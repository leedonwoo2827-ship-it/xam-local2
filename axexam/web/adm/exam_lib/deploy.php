<?php
if (!defined('_GNUBOARD_')) exit;

/**
 * 정적 파일 반입 — ZIP 하나를 받아 `/exam/pd/<pd>/` 또는 `/exam/` 에 풀어 넣는다.
 *
 * ── 왜 필요한가 ────────────────────────────────────────────────────────────
 * 문항 데이터는 이미 FTP 를 벗어났다(`adm/exam_import.php` → `ex_problem`). 그런데
 * **정적 산출물**(`problems.js` · `videos.js` · `theory*.js` · `figs/*.svg`)은 아직
 * FileZilla 뿐이다. 그래서 시험운용자를 늘릴 수 없다 — FTP 계정을 사람마다 줄 수는
 * 없기 때문이다. 이 화면이 그 마지막 칸을 메운다.
 *
 * ── ★ `.php` 는 받지 않는다 ────────────────────────────────────────────────
 * `/www/exam/` 에는 `brand.php` 가 있고 `/www/adm/` 에는 관리자 화면이 있다.
 * `.php` 를 받는 통로를 열면 그건 **서버에서 임의 코드를 실행하는 경로**가 된다.
 * 다행히 자동화에서 빠지는 것들은 거의 바뀌지 않는다(사이트 구조를 고칠 때만).
 * 그래서 PHP·테마·스킨은 계속 FTP 로 올린다. 여기서 받는 것은 콘텐츠뿐이다.
 *
 * ── ★ `problems.json` 도 받지 않는다 ───────────────────────────────────────
 * 그건 파일로 두는 것이 아니라 임포트 화면으로 DB 에 넣는 것이다
 * (`/exam/.htaccess` 가 `.json` 을 403 으로 막는 이유도 그것이다).
 * ZIP 에 섞여 있으면 조용히 넘기지 않고 **어디로 가야 하는지 알려준다.**
 *
 * ── 미리보기와 반입을 나눈다 ───────────────────────────────────────────────
 * `ex_deploy_inspect()` 는 아무것도 쓰지 않는다. 무엇이 새로 생기고 무엇이
 * 갈아끼워지고 무엇이 이미 같은지 표로 보여준 뒤에 `ex_deploy_apply()` 를 부른다.
 * FTP 는 이걸 못 해서 "올렸는데 반영이 안 된다" 의 원인을 늘 나중에 알았다.
 *
 * ── 시간 제한이 실질적 제약이다 ────────────────────────────────────────────
 * 카페24 실측: `upload_max_filesize 100M` · `post_max_size 100M` 이지만
 * **`max_execution_time 30`** 이다. `figs/` 가 235~245개라 넉넉하지만 무한하지 않다 —
 * 그래서 항목 수·총 크기 상한을 두고, 넘으면 나눠 올리라고 말한다.
 */

/* 임포트(`exam_lib/problem.php`)·품목 관리(`seed_pd.php`)와 **같은** 규칙이어야 한다.
   여기서 통과한 값이 거기서 막히면 원인을 찾을 데가 없다. */
define('EX_DEPLOY_PD_RE', '/^[a-z0-9\-]{1,20}$/');

/* 상한. 시간(30초)이 진짜 제약이라 크기보다 **항목 수**를 먼저 본다. */
define('EX_DEPLOY_MAX_ENTRIES', 600);
define('EX_DEPLOY_MAX_TOTAL',   12 * 1024 * 1024);   // 압축 풀린 합계
define('EX_DEPLOY_MAX_ONE',      4 * 1024 * 1024);   // 파일 하나

/**
 * 반입 대상 정의.
 *
 *   pd    품목 콘텐츠 — 빌드가 `06/pd/<pd>/` 에 만든 것. 거의 매번 바뀐다.
 *   shell 공용 껍데기 — `detail.html` 은 품목마다 만들지 않는다(한 장이 `?pd=` 로
 *         전부 렌더한다). 구조를 바꿀 때만 바뀌므로 확인을 한 번 더 받는다.
 */
function ex_deploy_targets()
{
    return array(
        'pd' => array(
            'label'  => '품목 콘텐츠',
            'server' => '/exam/pd/<pd>/',
            'ext'    => array('js', 'json', 'svg', 'html', 'css'),
            'note'   => 'problems.js · videos.js · theory.js · theory_content.js · figs/ · theory/',
        ),
        'shell' => array(
            'label'  => '공용 껍데기',
            'server' => '/exam/',
            'ext'    => array('html', 'css', 'js'),
            'note'   => 'index.html · detail.html · check.html · <pd>.html · assets/',
        ),
    );
}

/** 대상의 서버 실제 경로. 품목이면 `<웹루트>/exam/pd/<pd>`. */
function ex_deploy_root($target, $pd)
{
    $base = G5_PATH . '/exam';
    if ($target === 'shell') return $base;
    return $base . '/pd/' . $pd;
}

/** 사람에게 보여줄 서버 경로. */
function ex_deploy_server_path($target, $pd)
{
    return $target === 'shell' ? '/exam/' : '/exam/pd/' . $pd . '/';
}

/**
 * ZIP 항목 이름을 정리하고 검증한다.
 *
 * 돌려주는 것: 정리된 상대경로, 또는 거부 이유가 담긴 배열 `array('bad' => '이유')`.
 *
 * ★ zip slip — 항목 이름에 `..` 이나 절대경로가 들어오면 목적지 **밖**에 파일을 쓴다.
 *   그건 곧 `/www/adm/` 에 파일을 놓을 수 있다는 뜻이다. 문자열 단계에서 끊는다.
 */
function ex_deploy_clean_name($raw, $target, $pd)
{
    $name = str_replace('\\', '/', (string)$raw);

    if ($name === '' || substr($name, -1) === '/') return null;          // 디렉터리 항목
    if (strpos($name, "\0") !== false) return array('bad' => '이름에 널 바이트');
    if ($name[0] === '/') return array('bad' => '절대경로');
    if (preg_match('#^[A-Za-z]:#', $name)) return array('bad' => '드라이브 경로');

    /* 압축할 때 어디를 눌렀는지에 따라 접두어가 붙는다. 셋 다 받아준다:
         problems.js  ·  <pd>/problems.js  ·  pd/<pd>/problems.js  ·  06/pd/<pd>/... */
    $strip = array('06/pd/' . $pd . '/', 'pd/' . $pd . '/', $pd . '/', '06/');
    foreach ($strip as $pre) {
        if (strncmp($name, $pre, strlen($pre)) === 0) {
            $name = substr($name, strlen($pre));
            break;
        }
    }
    if ($name === '') return null;

    $out = array();
    foreach (explode('/', $name) as $seg) {
        if ($seg === '' || $seg === '.' || $seg === '..') {
            return array('bad' => '경로에 ' . ($seg === '..' ? '..' : '빈 칸') . ' 이 있습니다');
        }
        if (preg_match('/[<>:"|?*]/', $seg)) return array('bad' => '이름에 쓸 수 없는 글자');
        $out[] = $seg;
    }
    $rel = implode('/', $out);

    /* 확장자 화이트리스트. `.php` 는 여기서 반드시 걸린다. */
    $t = ex_deploy_targets();
    $ext = strtolower(pathinfo($rel, PATHINFO_EXTENSION));
    if ($ext === 'php' || $ext === 'phtml' || $ext === 'php5' || $ext === 'inc') {
        return array('bad' => 'PHP 는 받지 않습니다 — FTP 로 올리십시오');
    }
    if (!in_array($ext, $t[$target]['ext'], true)) {
        return array('bad' => '.' . $ext . ' 는 이 대상에서 받지 않습니다');
    }

    /* problems.json 은 파일이 아니라 임포트로 간다. */
    if (basename($rel) === 'problems.json') {
        return array('bad' => '문제 임포트 화면으로 올리십시오 (파일로 두지 않습니다)');
    }

    return $rel;
}

/** 목적지 절대경로가 뿌리 안에 있는지 — 문자열 검증을 통과한 뒤의 이중 확인. */
function ex_deploy_inside($root, $dest)
{
    $r = rtrim(str_replace('\\', '/', $root), '/') . '/';
    $d = str_replace('\\', '/', $dest);
    return strncmp($d, $r, strlen($r)) === 0;
}

/**
 * ZIP 을 열어 **판정만** 낸다. 아무것도 쓰지 않는다.
 *
 * 돌려주는 것:
 *   ok, error, target, pd, server, rows[], counts{new,replace,same}, rejected[],
 *   total_bytes, entries
 * rows 항목: rel, bytes, verdict(new|replace|same), dest
 */
function ex_deploy_inspect($zip_path, $target, $pd)
{
    $t = ex_deploy_targets();
    $out = array(
        'ok' => false, 'error' => '', 'target' => $target, 'pd' => $pd,
        'server' => ex_deploy_server_path($target, $pd),
        'rows' => array(), 'rejected' => array(),
        'counts' => array('new' => 0, 'replace' => 0, 'same' => 0),
        'total_bytes' => 0, 'entries' => 0,
    );

    if (!isset($t[$target])) { $out['error'] = '모르는 대상: ' . $target; return $out; }
    if (!preg_match(EX_DEPLOY_PD_RE, $pd)) {
        $out['error'] = "품목 코드 형식이 잘못됐습니다: '" . $pd . "' — 소문자·숫자·- 만, 20자 이내.";
        return $out;
    }
    if (!class_exists('ZipArchive')) {
        $out['error'] = '서버에 ZipArchive 확장이 없습니다. 호스팅에 문의하거나 FTP 로 올리십시오.';
        return $out;
    }

    $zip = new ZipArchive();
    if ($zip->open($zip_path) !== true) {
        $out['error'] = 'ZIP 을 열지 못했습니다. 파일이 깨졌거나 ZIP 이 아닙니다.';
        return $out;
    }

    $n = $zip->numFiles;
    $out['entries'] = $n;
    if ($n > EX_DEPLOY_MAX_ENTRIES) {
        $zip->close();
        $out['error'] = '항목이 ' . $n . '개입니다 (상한 ' . EX_DEPLOY_MAX_ENTRIES . '개). '
                      . 'figs/ 만, 본문만 처럼 나눠 올리십시오 — 서버 실행 시간이 '
                      . ini_get('max_execution_time') . '초입니다.';
        return $out;
    }

    $root = ex_deploy_root($target, $pd);
    $total = 0;

    for ($i = 0; $i < $n; $i++) {
        $st = $zip->statIndex($i);
        if ($st === false) continue;
        $rel = ex_deploy_clean_name($st['name'], $target, $pd);
        if ($rel === null) continue;                       // 디렉터리
        if (is_array($rel)) {
            $out['rejected'][] = array('name' => $st['name'], 'why' => $rel['bad']);
            continue;
        }
        $size = (int)$st['size'];
        if ($size > EX_DEPLOY_MAX_ONE) {
            $out['rejected'][] = array('name' => $rel,
                'why' => '파일 하나가 너무 큽니다 (' . ex_deploy_kb($size) . ')');
            continue;
        }
        $total += $size;

        $dest = $root . '/' . $rel;
        if (!ex_deploy_inside($root, $dest)) {
            $out['rejected'][] = array('name' => $rel, 'why' => '목적지가 대상 폴더 밖입니다');
            continue;
        }

        /* 판정. 「이미 같음」을 따로 세는 이유: 245개를 올렸는데 실제로 바뀐 것이
           3개라는 사실이 보여야 한다. FTP 는 그걸 알려주지 않았다. */
        $verdict = 'new';
        if (is_file($dest)) {
            $cur = @file_get_contents($dest);
            $new = $zip->getFromIndex($i);
            $verdict = ($cur !== false && $new !== false && $cur === $new) ? 'same' : 'replace';
        }
        $out['counts'][$verdict]++;
        $out['rows'][] = array('rel' => $rel, 'bytes' => $size,
                               'verdict' => $verdict, 'dest' => $dest);
    }
    $zip->close();

    $out['total_bytes'] = $total;
    if ($total > EX_DEPLOY_MAX_TOTAL) {
        $out['error'] = '압축을 풀면 ' . ex_deploy_kb($total) . ' 입니다 (상한 '
                      . ex_deploy_kb(EX_DEPLOY_MAX_TOTAL) . '). 나눠 올리십시오.';
        return $out;
    }
    if (!$out['rows'] && !$out['rejected']) {
        $out['error'] = '받을 수 있는 파일이 ZIP 안에 없습니다. '
                      . $t[$target]['label'] . ' 는 ' . implode('·', $t[$target]['ext'])
                      . ' 만 받습니다.';
        return $out;
    }

    $out['ok'] = true;
    return $out;
}

/**
 * 판정대로 쓴다. 미리보기를 그대로 다시 계산하므로 화면이 보낸 목록을 믿지 않는다.
 *
 * 「이미 같음」은 건드리지 않는다 — mtime 이 바뀌면 `check.php` 의 캐시 무효화가
 * 헛돌고, 무엇이 실제로 바뀌었는지도 서버에서 알 수 없게 된다.
 */
function ex_deploy_apply($zip_path, $target, $pd, $admin_id = '')
{
    $rep = ex_deploy_inspect($zip_path, $target, $pd);
    $rep['written'] = 0;
    $rep['skipped'] = 0;
    $rep['failed']  = array();
    if (!$rep['ok']) return $rep;

    $zip = new ZipArchive();
    if ($zip->open($zip_path) !== true) {
        $rep['ok'] = false;
        $rep['error'] = 'ZIP 을 두 번째로 열지 못했습니다.';
        return $rep;
    }

    $root = ex_deploy_root($target, $pd);
    $index = array();                                  // rel → 항목 번호
    for ($i = 0; $i < $zip->numFiles; $i++) {
        $st = $zip->statIndex($i);
        if ($st === false) continue;
        $rel = ex_deploy_clean_name($st['name'], $target, $pd);
        if (is_string($rel)) $index[$rel] = $i;
    }

    foreach ($rep['rows'] as $r) {
        if ($r['verdict'] === 'same') { $rep['skipped']++; continue; }
        if (!isset($index[$r['rel']])) {
            $rep['failed'][] = $r['rel'] . ' — ZIP 에서 다시 찾지 못했습니다';
            continue;
        }
        $data = $zip->getFromIndex($index[$r['rel']]);
        if ($data === false) {
            $rep['failed'][] = $r['rel'] . ' — 압축을 풀지 못했습니다';
            continue;
        }
        $dir = dirname($r['dest']);
        if (!is_dir($dir) && !@mkdir($dir, 0755, true)) {
            $rep['failed'][] = $r['rel'] . ' — 폴더를 만들지 못했습니다: ' . $dir;
            continue;
        }
        /* 임시 파일에 쓰고 rename — 쓰는 중에 그 파일을 요청한 사람이 잘린 파일을
           받지 않게 한다. problems.js 는 1MB 라 그 사이가 실제로 존재한다. */
        $tmp = $r['dest'] . '.tmp.' . getmypid();
        if (@file_put_contents($tmp, $data) === false || !@rename($tmp, $r['dest'])) {
            @unlink($tmp);
            $rep['failed'][] = $r['rel'] . ' — 쓰지 못했습니다 (권한을 확인하십시오)';
            continue;
        }
        $rep['written']++;
    }
    $zip->close();

    /* ★ 반입 이력을 남긴다. 지금까지 "무엇이 언제 올라갔나" 를 아는 방법이 없었다 —
       FTP 는 기록을 남기지 않고, 임포트 리포트는 화면에 한 번 뜨고 사라졌다.
       `ex_log` 는 이미 있는 테이블이다(qna·grade 가 쓴다). */
    if (function_exists('ex_deploy_log')) {
        ex_deploy_log($admin_id, $target . ':' . $pd, $rep['written']);
    }
    return $rep;
}

/** `ex_log` 에 한 줄. 이 테이블이 「언제 무엇이 올라갔나」의 유일한 기록이 된다. */
function ex_deploy_log($mb_id, $ref, $n)
{
    $mb  = sql_escape_string((string)$mb_id);
    $ref = sql_escape_string(substr($ref . ' x' . (int)$n, 0, 40));
    $ip  = sql_escape_string(function_exists('get_real_client_ip')
                             ? get_real_client_ip() : (isset($_SERVER['REMOTE_ADDR'])
                             ? $_SERVER['REMOTE_ADDR'] : ''));
    sql_query("insert into ex_log (mb_id, lo_act, lo_ref, lo_ip)
               values ('$mb', 'deploy', '$ref', '$ip')", false);
}

/**
 * 옛 납작 사본 찾기 — FTP 가 남긴 찌꺼기.
 *
 * ★ 실제로 있는 문제다. 예전 빌드는 `06/` 루트에 납작하게 만들어서
 *   `/exam/problems.js` 로 올라갔다. 그 뒤 `pd/<pd>/` 로 내렸지만 **FTP 는 지우지
 *   않으므로** 옛 파일이 서버에 그대로 남는다. `axexam/scripts/deploy_check.py` 가
 *   같은 것을 경고한다. 정답·해설이 담긴 파일이라 둘 이유가 없다.
 */
function ex_deploy_orphans()
{
    $names = array('problems.js', 'problems.json', 'videos.js', 'videos.private.json',
                   'theory.js', 'theory_content.js');
    $out = array();
    foreach ($names as $n) {
        $p = G5_PATH . '/exam/' . $n;
        if (is_file($p)) {
            $out[] = array('rel' => $n, 'path' => $p,
                           'bytes' => (int)@filesize($p), 'mtime' => (int)@filemtime($p));
        }
    }
    foreach (array('figs', 'theory') as $d) {
        $p = G5_PATH . '/exam/' . $d;
        if (is_dir($p)) {
            $g = @glob($p . '/*');
            $out[] = array('rel' => $d . '/', 'path' => $p,
                           'bytes' => 0, 'mtime' => (int)@filemtime($p),
                           'files' => is_array($g) ? count($g) : 0);
        }
    }
    return $out;
}

/** 납작 사본 하나 지우기. 이름 화이트리스트라 경로를 받지 않는다. */
function ex_deploy_remove_orphan($rel)
{
    $found = null;
    foreach (ex_deploy_orphans() as $o) {
        if ($o['rel'] === $rel) { $found = $o; break; }
    }
    if (!$found) return '그런 잔존물이 없습니다: ' . $rel;

    if (substr($rel, -1) === '/') {
        return '폴더는 여기서 지우지 않습니다 — ' . $found['path']
             . ' 를 FTP 로 확인한 뒤 지우십시오 (안에 무엇이 있는지 보고 지워야 합니다).';
    }
    return @unlink($found['path']) ? '' : '지우지 못했습니다 (권한): ' . $found['path'];
}

/**
 * 서버에 지금 무엇이 있나 — 품목 폴더의 실제 파일 목록.
 * 로컬과 비교할 근거다. FTP 는 "올렸다" 를 기록하지 않으므로 서버에 묻는 것이 유일한 진실이다.
 */
function ex_deploy_server_state($pd)
{
    $root = G5_PATH . '/exam/pd/' . $pd;
    $out = array('root' => $root, 'exists' => is_dir($root), 'files' => array(),
                 'dirs' => array(), 'bytes' => 0);
    if (!$out['exists']) return $out;

    $g = @glob($root . '/*');
    if (!is_array($g)) return $out;
    foreach ($g as $p) {
        if (is_dir($p)) {
            $inner = @glob($p . '/*');
            $n = is_array($inner) ? count($inner) : 0;
            $b = 0;
            if (is_array($inner)) foreach ($inner as $q) $b += (int)@filesize($q);
            $out['dirs'][] = array('name' => basename($p) . '/', 'files' => $n,
                                   'bytes' => $b, 'mtime' => (int)@filemtime($p));
            $out['bytes'] += $b;
        } else {
            $b = (int)@filesize($p);
            $out['files'][] = array('name' => basename($p), 'bytes' => $b,
                                    'mtime' => (int)@filemtime($p));
            $out['bytes'] += $b;
        }
    }
    return $out;
}

/** 서버에 등록된 품목 코드 목록 — 반입 대상 고르는 칸이 쓴다. */
function ex_deploy_pd_list()
{
    $out = array();
    $res = sql_query("select pd_id, pd_name, pd_open from ex_product
                      order by pd_sort, pd_id", false);
    if ($res) {
        while ($r = sql_fetch_array($res)) $out[] = $r;
    }
    return $out;
}

/**
 * 여기 올리는 「큰 주제」 — 5개다.
 *
 * ★ 왜 주제로 묶는가
 *   파일 목록으로 보여주면 245개가 한 줄씩 뜨고, 정작 알고 싶은 것("영상 링크는
 *   올라갔나?")은 그 안에 묻힌다. 사람이 하는 일은 파일 단위가 아니라 주제 단위다 —
 *   좌표를 고쳤으면 영상 링크만, 오탈자를 고쳤으면 문항만 간다.
 *
 * req: need = 하나라도 없으면 미완성 · any = 그룹에서 하나만 있으면 됨 · opt = 없어도 됨
 *   `videos.js` 와 `videos.private.json` 이 `any` 인 이유: 둘 중 하나만 생긴다.
 *
 * dirs 의 **세 번째 칸**은 그 폴더가 받는 확장자다. 낱개로 새 파일을 넣을 때
 * 이름만 보고 갈 자리를 정하는 근거가 된다(`ex_deploy_add_rel()`) — 서버가
 * 텅 비어 있어도 정해진다. 이걸 「이미 그 폴더에 있는 파일의 확장자」로
 * 추측하면 **처음 올릴 때** 갈 곳을 못 찾는다(실측으로 걸렸다).
 *   `min_level` 이 1 이하면 공개 `videos.js`, 2 이상이면 `videos.private.json` 이다.
 */
/**
 * 파일 하나가 **무엇인가** — 「빠짐: theory.js」 만 보고는 그게 목차인지 본문인지
 * 알 수 없다. 이론 영상 링크가 `theory.js` 안에 들어간다는 것이 특히 안 보였다
 * (2026-08-26 지적). 파일 이름 뒤에 한 마디를 붙인다.
 */
function ex_deploy_role($name)
{
    $ROLE = array(
        'theory.js' => '목차 + 이론 영상 링크 (url)',
    );
    return isset($ROLE[$name]) ? $ROLE[$name] : '';
}

/** 「빠짐」 목록을 「파일 — 무엇」 꼴로. */
function ex_deploy_missing_text($missing, $limit = 2)
{
    $out = array();
    foreach (array_slice($missing, 0, $limit) as $m) {
        $r = ex_deploy_role($m);
        $out[] = $r === '' ? $m : ($m . ' — ' . $r);
    }
    return implode(', ', $out);
}

function ex_deploy_topics()
{
    return array(
        array(
            'key' => 'problems', 'label' => '문항', 'target' => 'pd', 'import' => true,
            'files' => array(array('problems.js', 'need')),
            'dirs'  => array(),
            'note'  => '문제·보기·정답·해설. 서버에서는 DB(api/problems.php)가 이기고 '
                     . '이 파일은 정적 폴백입니다. 그래서 문항을 고치면 이 파일과 '
                     . '문제 임포트를 함께 해야 합니다.',
        ),
        array(
            'key' => 'videos', 'label' => '해설 영상 링크', 'target' => 'pd', 'import' => false,
            'files' => array(array('videos.js', 'any'), array('videos.private.json', 'any')),
            'dirs'  => array(),
            'note'  => '번들별 드라이브·유튜브 링크. 영상 파일 자체는 여기로 오지 않습니다. '
                     . 'videos.private.json 은 api/videos.php 가 요청마다 다시 읽으므로 '
                     . '그 한 파일만 올리면 즉시 반영됩니다.',
        ),
        array(
            'key' => 'theory', 'label' => '요약노트 (이론)', 'target' => 'pd', 'import' => false,
            'files' => array(array('theory.js', 'need'), array('theory_content.js', 'need')),
            'dirs'  => array(array('theory', 'opt', 'js')),
            'note'  => 'theory.js 는 과목별 강의 링크, theory_content.js 는 본문입니다. '
                     . '이론은 DB 가 아니라 이 파일에 구워져 있습니다. '
                     . 'theory/summary_*.js 는 과목 하나씩 담은 같은 본문이라 '
                     . '주제 합계가 본문의 두 배로 보입니다 — 화면이 읽는 것은 '
                     . 'theory_content.js 뿐이고, 그 파일들은 과목별 갈음의 단위입니다.',
        ),
        array(
            'key' => 'figs', 'label' => '문제 도식', 'target' => 'pd', 'import' => false,
            'files' => array(),
            'dirs'  => array(array('figs', 'need', 'svg')),
            'note'  => '문제에 딸린 SVG 도식. **문항이 이것을 불러 씁니다** — '
                     . 'problems.js 가 파일명으로 가리키므로 둘을 같이 올려야 그림이 '
                     . '나옵니다(빅분기 실측 235개 중 167개 사용). 요약노트는 그림을 '
                     . 'HTML 안에 인라인으로 담아서 이 폴더를 쓰지 않습니다. '
                     . '개수가 많아 시간 제한에 가장 먼저 걸리는 주제입니다 — '
                     . '넘치면 이것만 따로 올리십시오.',
        ),
        array(
            'key' => 'shell', 'label' => '공용 껍데기', 'target' => 'shell', 'import' => false,
            'files' => array(array('index.html', 'need'), array('detail.html', 'need'),
                             array('check.html', 'opt')),
            'dirs'  => array(array('assets', 'opt', 'css,js,html,svg')),
            'note'  => '모든 문제집이 함께 씁니다 — detail.html 한 장이 ?pd= 로 전부 '
                     . '렌더합니다. 품목마다 만들지 않습니다. 구조를 바꿀 때만 갑니다. '
                     . 'brand.php 는 PHP 라 여기서 받지 않습니다(FTP).',
        ),
    );
}

/** 주제 하나를 키로 찾는다. 없으면 null. */
function ex_deploy_topic($key)
{
    foreach (ex_deploy_topics() as $t) {
        if ($t['key'] === $key) return $t;
    }
    return null;
}

/**
 * 주제 하나가 서버에 지금 어떤 상태인가.
 *
 * FTP 는 「올렸다」를 기록하지 않으므로 서버 파일을 직접 보는 것이 유일한 진실이다.
 * 돌려주는 것: state(ok|part|none), items[], bytes, mtime
 */
function ex_deploy_topic_state($t, $pd)
{
    $base = ($t['target'] === 'shell') ? G5_PATH . '/exam' : G5_PATH . '/exam/pd/' . $pd;
    $out = array('items' => array(), 'bytes' => 0, 'mtime' => 0,
                 'state' => 'none', 'missing' => array());

    $need_ok = true; $any_seen = false; $any_exists = false; $some = false;

    foreach ($t['files'] as $f) {
        list($name, $req) = $f;
        $p = $base . '/' . $name;
        $ok = is_file($p);
        $b = $ok ? (int)@filesize($p) : 0;
        $m = $ok ? (int)@filemtime($p) : 0;
        if ($req === 'any') { $any_seen = true; if ($ok) $any_exists = true; }
        if ($req === 'need' && !$ok) { $need_ok = false; $out['missing'][] = $name; }
        if ($ok) { $some = true; $out['bytes'] += $b; if ($m > $out['mtime']) $out['mtime'] = $m; }
        $out['items'][] = array('name' => $name, 'req' => $req, 'ok' => $ok,
                                'bytes' => $b, 'mtime' => $m, 'dir' => false);
    }

    foreach ($t['dirs'] as $d) {
        list($name, $req) = $d;
        $p = $base . '/' . $name;
        $ok = is_dir($p);
        $n = 0; $b = 0; $m = $ok ? (int)@filemtime($p) : 0;
        if ($ok) {
            $g = @glob($p . '/*');
            if (is_array($g)) {
                $n = count($g);
                foreach ($g as $q) if (is_file($q)) $b += (int)@filesize($q);
            }
        }
        /* 빈 폴더는 "있다" 로 치지 않는다 — 실측으로 빅분기의 theory/ 가 0개였다.
           폴더만 있고 안이 비면 화면에는 아무것도 안 나온다. */
        $has = ($ok && $n > 0);
        if ($req === 'need' && !$has) { $need_ok = false; $out['missing'][] = $name . '/'; }
        if ($has) { $some = true; $out['bytes'] += $b; if ($m > $out['mtime']) $out['mtime'] = $m; }
        $out['items'][] = array('name' => $name . '/', 'req' => $req, 'ok' => $has,
                                'bytes' => $b, 'mtime' => $m, 'dir' => true, 'files' => $n);
    }

    if ($any_seen && !$any_exists) { $need_ok = false; $out['missing'][] = '영상 링크 파일'; }

    if ($need_ok) $out['state'] = 'ok';
    elseif ($some) $out['state'] = 'part';
    else $out['state'] = 'none';
    return $out;
}

function ex_deploy_kb($n)
{
    $n = (int)$n;
    if ($n >= 1024 * 1024) return number_format($n / (1024 * 1024), 1) . 'MB';
    if ($n >= 1024) return number_format($n / 1024, 1) . 'KB';
    return $n . 'B';
}

/* ───────────────────────────────────────────────────────────────────────────
   여기부터: 「서버에 실제로 무엇이 있나」와 **파일 하나만 갈아끼우기**

   위쪽 함수들은 ZIP 통로다. 아래는 그것과 짝을 이루는 낱개 통로다.
   ★ 검증 규칙을 새로 만들지 않는다 — `ex_deploy_clean_name()` ·
     `ex_deploy_inside()` · `EX_DEPLOY_MAX_ONE` 을 그대로 쓴다. 두 통로의 허용
     범위가 갈라지면 한쪽에서 통과한 것이 다른 쪽에서 막히고, 원인을 찾을 데가 없다.
   ─────────────────────────────────────────────────────────────────────── */

/** 임시 파일에 쓰고 rename — 쓰는 중에 그 파일을 요청한 사람이 잘린 파일을 받지 않게 한다. */
function ex_deploy_put($path, $data)
{
    $dir = dirname($path);
    if (!is_dir($dir) && !@mkdir($dir, 0755, true)) return '폴더를 만들지 못했습니다: ' . $dir;
    $tmp = $path . '.tmp.' . getmypid();
    if (@file_put_contents($tmp, $data) === false || !@rename($tmp, $path)) {
        @unlink($tmp);
        return '쓰지 못했습니다 (권한을 확인하십시오): ' . $path;
    }
    return '';
}

/** 파일 한 줄을 목록에 넣는다. 상한을 넘으면 넣지 않고 세기만 한다. */
function ex_deploy_push_row(&$out, $rel, $path)
{
    $b = (int)@filesize($path);
    $m = (int)@filemtime($path);
    $out['bytes'] += $b;
    if ($m > $out['mtime']) $out['mtime'] = $m;
    if (count($out['rows']) >= EX_DEPLOY_MAX_ENTRIES) { $out['cut']++; return; }
    $out['rows'][] = array(
        'rel'   => $rel,
        'name'  => basename($rel),
        'sub'   => (strpos($rel, '/') === false) ? '' : dirname($rel),
        'bytes' => $b,
        'mtime' => $m,
    );
}

/** 폴더 하나를 훑는다. 깊이 제한 — `theory/assets/` · `assets/` 때문에 2가 필요하다. */
function ex_deploy_walk($base, $rel, &$out, $depth)
{
    $p = $base . '/' . $rel;
    if (!is_dir($p)) return;
    $g = @glob($p . '/*');
    if (!is_array($g)) return;
    sort($g);
    foreach ($g as $q) {
        $r = $rel . '/' . basename($q);
        if (is_dir($q)) {
            if ($depth > 1) ex_deploy_walk($base, $r, $out, $depth - 1);
            continue;
        }
        ex_deploy_push_row($out, $r, $q);
    }
}

/**
 * 주제 하나에 **실제로 있는** 파일 목록.
 *
 * `ex_deploy_topic_state()` 와 무엇이 다른가: 그것은 **선언된 항목**의 상태를 돌려주고
 * 폴더는 `count(glob())` 로 세기만 한다(파일명을 버린다). 그래서 화면에 「figs/ 479개」
 * 까지만 나왔고 "그 안에 무엇이 있나" 는 알 방법이 없었다. 이 함수가 그 이름들을 준다.
 *
 * ★ 없는 파일은 줄로 넣지 않는다. 서버에 아무것도 없는 품목의 박스는 **비어야** 한다
 *   (지금 sqld 의 문항). 빠진 것은 위 주제 박스가 「빠짐: problems.js」로 이미 말한다.
 *
 * 돌려주는 것: rows[](rel·name·sub·bytes·mtime) · bytes · mtime · cut(상한에 걸려 뺀 수)
 */
function ex_deploy_topic_files($t, $pd)
{
    $base = ($t['target'] === 'shell') ? G5_PATH . '/exam' : G5_PATH . '/exam/pd/' . $pd;
    $out  = array('rows' => array(), 'bytes' => 0, 'mtime' => 0, 'cut' => 0);

    foreach ($t['files'] as $f) {
        $p = $base . '/' . $f[0];
        if (is_file($p)) ex_deploy_push_row($out, $f[0], $p);
    }
    foreach ($t['dirs'] as $d) {
        ex_deploy_walk($base, $d[0], $out, 2);
    }
    return $out;
}

/**
 * 갈아끼울 수 있는 자리인가 — 화면이 보낸 `rel` 을 **믿지 않는다.**
 *
 * `ex_deploy_remove_orphan()` 과 같은 방식이다: 경로를 받아 쓰는 것이 아니라
 * **서버에 실제로 있는 것**(+ 주제에 선언된 것) 목록과 대조한다. 거기에 없으면 거부다.
 * 그 뒤 문자열 검증(`ex_deploy_clean_name`)과 경로 검증(`ex_deploy_inside`)을 또 통과해야 한다.
 *
 * 돌려주는 것: array('dest' => 절대경로) 또는 array('bad' => '이유')
 */
function ex_deploy_replace_dest($target, $pd, $rel)
{
    $T = ex_deploy_targets();
    if (!isset($T[$target])) return array('bad' => '모르는 대상: ' . $target);
    if ($target !== 'shell' && !preg_match(EX_DEPLOY_PD_RE, $pd)) {
        return array('bad' => '품목 코드 형식이 잘못됐습니다: ' . $pd);
    }
    $rel = str_replace('\\', '/', (string)$rel);

    /* 화이트리스트 — 이 대상의 주제들이 실제로 가진 것 + 선언한 것 + 선언된 폴더 안.
       ★ 「선언된 폴더 안」을 받는 이유: ZIP 통로가 이미 `figs/*.svg` 든
         `theory/*.js` 든 받는다. 낱개 통로만 더 좁히면, ZIP 으로는 되는 일이
         파일 하나로는 안 되는 이상한 상태가 된다 — 두 통로의 허용 범위는 같아야 한다.
         임의 경로가 열리는 것은 아니다: 첫 칸이 선언된 폴더여야 하고, 그 뒤로도
         `ex_deploy_clean_name()`(`..`·`.php`·`problems.json` 차단)과
         `ex_deploy_inside()` 를 둘 다 통과해야 한다. */
    $white = array(); $dirs = array();
    foreach (ex_deploy_topics() as $t) {
        if ($t['target'] !== $target) continue;
        foreach ($t['files'] as $f) $white[$f[0]] = true;
        foreach ($t['dirs'] as $d)  $dirs[$d[0]] = true;
        $fl = ex_deploy_topic_files($t, $pd);
        foreach ($fl['rows'] as $r) $white[$r['rel']] = true;
    }
    $allow = isset($white[$rel]);
    if (!$allow) {
        $seg = explode('/', $rel);
        if (count($seg) >= 2 && isset($dirs[$seg[0]])) $allow = true;
    }
    if (!$allow) {
        return array('bad' => '넣을 수 있는 자리가 아닙니다: ' . $rel
                   . ' — 이 대상이 받는 것은 ' . implode(' · ', array_keys($white))
                   . ($dirs ? ' 과 ' . implode('/ · ', array_keys($dirs)) . '/ 안' : '')
                   . ' 입니다.');
    }

    /* ZIP 통로와 **같은** 문자열 규칙. `.php` · `problems.json` 이 여기서 걸린다. */
    $clean = ex_deploy_clean_name($rel, $target, $pd);
    if ($clean === null)  return array('bad' => '파일 이름이 비었습니다');
    if (is_array($clean)) return $clean;
    if ($clean !== $rel)  return array('bad' => '이름이 규칙을 지나며 바뀌었습니다: ' . $rel);

    $root = ex_deploy_root($target, $pd);
    $dest = $root . '/' . $rel;
    if (!ex_deploy_inside($root, $dest)) return array('bad' => '목적지가 대상 폴더 밖입니다');

    return array('dest' => $dest);
}

/**
 * 파일 **하나**를 갈아끼운다.
 *
 * ★ 확장자가 목적지와 다르면 거부한다 — problems.js 자리에 .html 을 떨구는 실수가
 *   조용히 통과하면 문제집이 통째로 빈다.
 * ★ 내용이 같으면 **쓰지 않는다.** `ex_deploy_apply()` 가 「이미 같음」을 건드리지 않는
 *   것과 같은 이유다 — mtime 이 바뀌면 `.htaccess` 1시간 캐시와 `check.php` 의 캐시
 *   무효화가 헛돌고, 무엇이 실제로 바뀌었는지도 서버에서 알 수 없게 된다.
 */
function ex_deploy_replace_one($target, $pd, $rel, $tmp, $up_name, $admin_id = '')
{
    $d = ex_deploy_replace_dest($target, $pd, $rel);
    if (isset($d['bad'])) return array('ok' => false, 'error' => $d['bad']);
    $dest = $d['dest'];

    $want = strtolower(pathinfo($rel, PATHINFO_EXTENSION));
    $got  = strtolower(pathinfo((string)$up_name, PATHINFO_EXTENSION));
    if ($got !== $want) {
        return array('ok' => false, 'error' => '올린 파일이 .' . $got . ' 입니다 — 이 자리는 .'
                   . $want . ' 입니다. 다른 줄에 떨어뜨린 것이 아닌지 보십시오.');
    }

    $size = (int)@filesize($tmp);
    if ($size > EX_DEPLOY_MAX_ONE) {
        return array('ok' => false, 'error' => '파일 하나가 너무 큽니다 ('
                   . ex_deploy_kb($size) . ' · 상한 ' . ex_deploy_kb(EX_DEPLOY_MAX_ONE) . ')');
    }
    $data = @file_get_contents($tmp);
    if ($data === false) return array('ok' => false, 'error' => '올린 파일을 읽지 못했습니다.');

    if (is_file($dest) && @file_get_contents($dest) === $data) {
        return array('ok' => true, 'same' => true, 'bytes' => $size, 'rel' => $rel,
                     'msg' => $rel . ' — 이미 같습니다. 건드리지 않았습니다.');
    }
    $new = !is_file($dest);
    $e = ex_deploy_put($dest, $data);
    if ($e !== '') return array('ok' => false, 'error' => $e);

    ex_deploy_log($admin_id, 'one ' . $pd . '/' . basename($rel), 1);
    return array('ok' => true, 'same' => false, 'bytes' => $size, 'rel' => $rel,
                 'msg' => $rel . ' — ' . ($new ? '새로 넣었습니다' : '갈아끼웠습니다')
                        . ' (' . ex_deploy_kb($size) . ').');
}

/* ───────────────────────────────────────────────────────────────────────────
   요약노트 — **과목 하나만** 갈아끼우기

   ★ 왜 따로 다루는가
     `theory_content.js` 는 4과목이 한 파일에 구워져 있다. 통째로 갈면 아직 안 만든
     과목이 옛 것으로 덮인다 — 빅분기에서 실제로 막힌 지점이다(4과목 중 3과목만 새로
     만들었다). 그래서 빌드가 **과목 하나 = 한 줄**로 굽고(`build_check.py` 의
     `write_theory_content()`), 여기서 **그 한 줄만** 바꿔 쓴다.

   ★ PHP 는 요약노트 HTML 을 파싱하지 않는다.
     굽는 로직(`<style>` 을 먼저 떼야 한다 — 2026-08-13 에 4과목이 전부 빈 그 함정)은
     `build_check.py` 에만 있다. 여기 한 벌 더 두면 언젠가 갈라지고, 갈라진 쪽이
     조용히 본문을 날린다. 그래서 받는 것은 **빌드가 만든 theory/summary_*.js** 다.
   ─────────────────────────────────────────────────────────────────────── */

define('EX_THEORY_GUARD', 'window.THEORY_HTML = window.THEORY_HTML || {};');

/** `window.<VAR> = …;` 한 줄짜리 JS 를 값으로. `theory.js` 를 읽는 데 쓴다. */
function ex_deploy_js_value($path, $var)
{
    $raw = @file_get_contents($path);
    if ($raw === false) return null;
    if (!preg_match('/^\s*window\.' . preg_quote($var, '/') . '\s*=\s*(.*?);\s*$/s', $raw, $m)) {
        return null;
    }
    return json_decode($m[1], true);
}

/**
 * `theory_content.js` 를 **줄 단위**로 읽는다.
 *
 * 돌려주는 것:
 *   head[]  과목 줄이 아닌 줄(주석·가드). 그대로 다시 쓴다.
 *   units[] 키 => **값 리터럴(원본 바이트 그대로)**. 디코드하지 않는 것이 핵심이다 —
 *           손대지 않은 과목은 다시 써도 바이트가 같아야 한다.
 *   old     옛 한 덩이 형식인가(그러면 과목별 갈음이 안 된다).
 */
function ex_deploy_theory_lines($path)
{
    $out = array('head' => array(), 'units' => array(), 'old' => false, 'err' => '');
    $raw = @file_get_contents($path);
    if ($raw === false) { $out['err'] = '읽지 못했습니다: ' . basename($path); return $out; }

    $lines = explode("\n", str_replace("\r\n", "\n", $raw));
    foreach ($lines as $ln) {
        $ln = rtrim($ln, "\r");
        if (preg_match('/^window\.THEORY_HTML\[("(?:[^"\\\\]|\\\\.)*")\]\s*=\s*(.*);\s*$/', $ln, $m)) {
            $k = json_decode($m[1], true);
            if (is_string($k) && $k !== '') { $out['units'][$k] = $m[2]; continue; }
        }
        if (trim($ln) !== '') $out['head'][] = $ln;
    }
    if (!$out['units'] && strpos($raw, 'window.THEORY_HTML') !== false) $out['old'] = true;
    return $out;
}

/** 줄 맵으로 `theory_content.js` 를 다시 만든다. 손대지 않은 과목은 바이트가 같다. */
function ex_deploy_theory_write($path, $head, $units)
{
    $body = $head;
    if (!$body) $body[] = EX_THEORY_GUARD;
    foreach ($units as $k => $lit) {
        $body[] = 'window.THEORY_HTML['
                . json_encode($k, JSON_UNESCAPED_SLASHES | JSON_UNESCAPED_UNICODE)
                . '] = ' . $lit . ';';
    }
    return ex_deploy_put($path, implode("\n", $body) . "\n");
}

/** 과목의 자립 파일 경로 — theory/summary_explore.html → <base>/theory/summary_explore.js */
function ex_deploy_theory_unit($base, $href)
{
    return $base . '/' . preg_replace('/\.html$/', '', (string)$href) . '.js';
}

/**
 * 화면이 쓰는 **과목 줄**. `theory.js`(이름·순서·강의 링크) + `theory_content.js`(본문) +
 * `theory/summary_*.js`(갈음 단위 · 과목별 시각)를 합친다.
 *
 * `synced=false` 는 단위 파일과 합본의 그 줄이 다르다는 뜻이다 — ZIP 으로 단위 파일만
 * 올리고 합본을 안 이은 경우다. 그 상태면 파일은 올라가 있는데 화면이 안 바뀌어서
 * 원인을 못 찾는다. 그래서 화면에 드러내고 [다시 이어붙이기] 를 준다.
 */
function ex_deploy_theory_index($pd)
{
    $base = G5_PATH . '/exam/pd/' . $pd;
    $out  = array('rows' => array(), 'old' => false, 'err' => '');

    $items = ex_deploy_js_value($base . '/theory.js', 'THEORY');
    $tc    = ex_deploy_theory_lines($base . '/theory_content.js');
    $out['old'] = $tc['old'];
    if (!is_array($items)) return $out;      // theory.js 가 없거나 못 읽었다 — 조용히 빈 목록

    foreach ($items as $it) {
        if (!is_array($it) || !isset($it['href'])) continue;
        $href = (string)$it['href'];
        $unit = ex_deploy_theory_unit($base, $href);
        $lit  = isset($tc['units'][$href]) ? $tc['units'][$href] : null;
        $uraw = is_file($unit) ? ex_deploy_theory_lines($unit) : null;
        $ulit = ($uraw && isset($uraw['units'][$href])) ? $uraw['units'][$href] : null;

        $out['rows'][] = array(
            'href'       => $href,
            'label'      => isset($it['label']) ? (string)$it['label'] : $href,
            'sub'        => isset($it['sub']) ? (int)$it['sub'] : 0,
            'vid'        => isset($it['vid']),
            'in_content' => ($lit !== null),
            'body_bytes' => ($lit !== null) ? strlen($lit) : 0,
            'unit_rel'   => 'theory/' . basename($unit),
            'unit_ok'    => is_file($unit),
            'unit_bytes' => is_file($unit) ? (int)@filesize($unit) : 0,
            'unit_mtime' => is_file($unit) ? (int)@filemtime($unit) : 0,
            /* 단위 파일이 아예 없으면 「어긋났다」고 말하지 않는다 — 옛 ZIP 으로 올린
               문제집은 합본만 있는 것이 정상이다. 둘 다 있을 때만 대조한다. */
            'synced'     => ($ulit === null || $lit === null) ? true : ($ulit === $lit),
        );
    }
    return $out;
}

/** 올린 파일에서 그 과목의 값 리터럴을 꺼낸다. 단위 파일이든 합본이든 받는다. */
function ex_deploy_theory_pick($tmp, $href)
{
    $p = ex_deploy_theory_lines($tmp);
    if ($p['err'] !== '') return array('bad' => $p['err']);
    if (!$p['units']) {
        return array('bad' => '올린 파일에서 과목 줄을 찾지 못했습니다. 빌드가 만든 '
                   . 'theory/summary_*.js 를 올리십시오'
                   . ($p['old'] ? ' (옛 형식입니다 — 다시 빌드하십시오)' : '') . '.');
    }
    if (!isset($p['units'][$href])) {
        return array('bad' => '올린 파일에 이 과목이 없습니다. 들어 있는 것: '
                   . implode(', ', array_map('basename', array_keys($p['units'])))
                   . ' · 이 줄이 기다리는 것: ' . basename($href));
    }
    return array('lit' => $p['units'][$href]);
}

/**
 * 과목 **하나**를 갈아끼운다 — ① 단위 파일을 쓰고 ② 합본의 그 한 줄만 갈아끼운다.
 * 둘이 같은 업로드 바이트에서 나오므로 어긋날 수 없다.
 */
function ex_deploy_theory_replace($pd, $href, $tmp, $up_name, $admin_id = '')
{
    if (!preg_match(EX_DEPLOY_PD_RE, $pd)) {
        return array('ok' => false, 'error' => '품목 코드 형식이 잘못됐습니다: ' . $pd);
    }
    if (strtolower(pathinfo((string)$up_name, PATHINFO_EXTENSION)) !== 'js') {
        return array('ok' => false, 'error' => '요약노트 과목은 빌드가 만든 '
                   . 'theory/summary_*.js 로 갈아끼웁니다. HTML 원본은 받지 않습니다 — '
                   . '굽는 곳은 빌드 한 곳뿐이어야 합니다.');
    }
    $size = (int)@filesize($tmp);
    if ($size > EX_DEPLOY_MAX_ONE) {
        return array('ok' => false, 'error' => '파일이 너무 큽니다 (' . ex_deploy_kb($size) . ')');
    }

    /* ★ POST 의 href 를 믿지 않는다 — theory.js 의 목록에 있어야 한다. */
    $idx = ex_deploy_theory_index($pd);
    $row = null;
    foreach ($idx['rows'] as $r) if ($r['href'] === $href) { $row = $r; break; }
    if (!$row) return array('ok' => false, 'error' => '그런 과목이 theory.js 에 없습니다: ' . $href);

    $pick = ex_deploy_theory_pick($tmp, $href);
    if (isset($pick['bad'])) return array('ok' => false, 'error' => $pick['bad']);
    $lit = $pick['lit'];

    $base = G5_PATH . '/exam/pd/' . $pd;
    $tc   = ex_deploy_theory_lines($base . '/theory_content.js');
    if ($tc['old']) {
        return array('ok' => false, 'error' => '서버의 theory_content.js 가 옛 한 덩이 '
                   . '형식입니다. 과목별로 갈아끼우려면 새로 빌드한 것을 ZIP 으로 한 번 '
                   . '올려 형식을 바꾸십시오(그 뒤로는 과목별로 됩니다).');
    }
    if (isset($tc['units'][$href]) && $tc['units'][$href] === $lit
        && is_file(ex_deploy_theory_unit($base, $href))) {
        return array('ok' => true, 'same' => true,
                     'msg' => $row['label'] . ' — 이미 같습니다. 건드리지 않았습니다.');
    }

    /* ① 단위 파일. 합본을 떨어뜨렸어도 여기에는 그 과목 한 줄만 정규화해 쓴다. */
    $e = ex_deploy_put(ex_deploy_theory_unit($base, $href),
                       EX_THEORY_GUARD . "\n" . 'window.THEORY_HTML['
                       . json_encode($href, JSON_UNESCAPED_SLASHES | JSON_UNESCAPED_UNICODE)
                       . '] = ' . $lit . ';' . "\n");
    if ($e !== '') return array('ok' => false, 'error' => $e);

    /* ② 합본의 그 줄만. 나머지 과목은 리터럴을 그대로 다시 써서 바이트가 같다. */
    $units = $tc['units'];
    $units[$href] = $lit;
    $e = ex_deploy_theory_write($base . '/theory_content.js', $tc['head'], $units);
    if ($e !== '') return array('ok' => false, 'error' => $e);

    ex_deploy_log($admin_id, 'thy ' . $pd . ' ' . $row['sub'] . '과목', 1);
    return array('ok' => true, 'same' => false,
                 'msg' => $row['label'] . ' 을 갈아끼웠습니다 (' . ex_deploy_kb($size)
                        . '). 나머지 과목은 건드리지 않았습니다.');
}

/** 서버에 이미 있는 단위 파일로 합본의 그 줄만 다시 잇는다 — 어긋난 상태의 복구다. */
function ex_deploy_theory_restitch($pd, $href, $admin_id = '')
{
    if (!preg_match(EX_DEPLOY_PD_RE, $pd)) {
        return array('ok' => false, 'error' => '품목 코드 형식이 잘못됐습니다: ' . $pd);
    }
    $idx = ex_deploy_theory_index($pd);
    $row = null;
    foreach ($idx['rows'] as $r) if ($r['href'] === $href) { $row = $r; break; }
    if (!$row) return array('ok' => false, 'error' => '그런 과목이 theory.js 에 없습니다: ' . $href);

    $base = G5_PATH . '/exam/pd/' . $pd;
    $unit = ex_deploy_theory_unit($base, $href);
    if (!is_file($unit)) {
        return array('ok' => false, 'error' => '단위 파일이 서버에 없습니다: '
                   . $row['unit_rel'] . ' — 먼저 그것을 올리십시오.');
    }
    $pick = ex_deploy_theory_pick($unit, $href);
    if (isset($pick['bad'])) return array('ok' => false, 'error' => $pick['bad']);

    $tc = ex_deploy_theory_lines($base . '/theory_content.js');
    if ($tc['old']) {
        return array('ok' => false, 'error' => '서버의 theory_content.js 가 옛 한 덩이 형식입니다.');
    }
    $units = $tc['units'];
    $units[$href] = $pick['lit'];
    $e = ex_deploy_theory_write($base . '/theory_content.js', $tc['head'], $units);
    if ($e !== '') return array('ok' => false, 'error' => $e);

    ex_deploy_log($admin_id, 'stitch ' . $pd . ' ' . $row['sub'] . '과목', 1);
    return array('ok' => true, 'same' => false,
                 'msg' => $row['label'] . ' 을 합본에 다시 이어붙였습니다.');
}

/* ───────────────────────────────────────────────────────────────────────────
   「만든 것 그대로 올리기」 — 새 파일도 낱개로 받는다

   ★ 목표: 빌드가 만든 것을 **그대로** 처음 올린다. 폴더가 끼는 것(도식 479개 ·
     공용 껍데기 assets/)만 ZIP 이고, 나머지는 파일을 그냥 골라 넣는다.
   ★ 그래서 올린 파일의 **이름만 보고** 갈 자리를 정해야 한다. 규칙은 데이터에서
     끌어낸다(주제 정의에 이미 다 있다) — 파일명을 코드에 박지 않는다.
   ─────────────────────────────────────────────────────────────────────── */

/**
 * 올린 파일 하나가 갈 자리(상대경로)를 정한다.
 *
 *   ① 어느 주제든 **선언한 파일 이름**과 같으면 그 자리(뿌리)다.
 *      problems.js · videos.js · theory.js · theory_content.js · index.html …
 *   ② 서버에 이미 그 이름으로 있으면 그 자리다(하위 폴더까지 이름이 맞을 때).
 *   ③ 그 대상의 **선언된 폴더 중, 같은 확장자를 이미 담고 있는 폴더**가 하나면 거기다.
 *      품목: `.svg` → `figs/` · `.js` → `theory/`  ·  껍데기: `.css`·`.js` → `assets/`
 *      후보가 둘 이상이면 정하지 않는다 — 주제의 [＋ 파일 넣기] 로 찍어 달라고 한다.
 *   ④ `$topic_key` 가 주어졌으면(주제의 ＋ 버튼) 그 주제의 첫 폴더를 쓴다.
 *
 * 돌려주는 것: array('rel' => '...', 'why' => '왜 거기인가') 또는 array('bad' => '이유')
 */
function ex_deploy_add_rel($target, $pd, $name, $topic_key = '')
{
    $name = (string)$name;
    /* ★ 경로가 섞인 이름은 **그냥 거부**한다. `basename()` 으로 조용히 깎으면
         `../../adm/pwn.js` 가 `theory/pwn.js` 로 들어가 버린다 — 폴더 밖으로 나가지는
         못하지만(뒤의 `ex_deploy_inside()` 가 막는다) 올린 사람은 어디로 갔는지 모른다.
         브라우저가 보내는 파일 이름에는 원래 경로가 없다. 있으면 정상이 아니다. */
    if (strpbrk($name, "/\\") !== false || strpos($name, "\0") !== false) {
        return array('bad' => $name . ' — 파일 이름에 경로가 섞여 있습니다. 받지 않습니다.');
    }
    $base = basename($name);
    if ($base === '' || $base === '.' || $base === '..') return array('bad' => '파일 이름이 없습니다');
    $ext = strtolower(pathinfo($base, PATHINFO_EXTENSION));

    $topics = array();
    foreach (ex_deploy_topics() as $t) if ($t['target'] === $target) $topics[] = $t;
    if (!$topics) return array('bad' => '모르는 대상: ' . $target);

    /* ① 선언된 파일 이름과 같은가 */
    foreach ($topics as $t) {
        foreach ($t['files'] as $f) {
            if ($f[0] === $base) {
                return array('rel' => $base, 'why' => $t['label'] . ' — 정해진 자리');
            }
        }
    }

    /* ② 서버에 이미 있는 이름인가 (하위 폴더 포함) */
    foreach ($topics as $t) {
        $fl = ex_deploy_topic_files($t, $pd);
        foreach ($fl['rows'] as $r) {
            if ($r['name'] === $base) {
                return array('rel' => $r['rel'], 'why' => $t['label'] . ' — 서버에 있던 자리');
            }
        }
    }

    /* ③ 그 확장자를 **받겠다고 선언한** 폴더가 하나뿐인가
         (주제 정의의 dirs 세 번째 칸. 서버가 텅 비어 있어도 정해진다 — 「이미 있는
          파일의 확장자」로 추측하면 처음 올릴 때 갈 곳을 못 찾는다.)
         품목: .svg → figs/ · .js → theory/   ·   껍데기: .css·.js → assets/ */
    $hit = array();
    foreach ($topics as $t) {
        foreach ($t['dirs'] as $d) {
            if (!isset($d[2]) || $d[2] === '') continue;
            if (!in_array($ext, explode(',', $d[2]), true)) continue;
            $hit[$d[0]] = $t['label'];
        }
    }
    if (count($hit) === 1) {
        $d = key($hit);
        return array('rel' => $d . '/' . $base, 'why' => $hit[$d] . ' — .' . $ext . ' 는 ' . $d . '/');
    }

    /* ④ 주제를 찍어 왔으면 그 주제의 첫 폴더 */
    if ($topic_key !== '') {
        $t = ex_deploy_topic($topic_key);
        if ($t && $t['target'] === $target && $t['dirs']) {
            return array('rel' => $t['dirs'][0][0] . '/' . $base,
                         'why' => $t['label'] . ' — ' . $t['dirs'][0][0] . '/');
        }
        if ($t && !$t['dirs']) {
            $nm = array();
            foreach ($t['files'] as $f) $nm[] = $f[0];
            return array('bad' => $base . ' — ' . $t['label'] . ' 이 받는 것은 '
                       . implode(' · ', $nm) . ' 뿐입니다. 이름을 확인하십시오.');
        }
    }

    if (count($hit) > 1) {
        return array('bad' => $base . ' — .' . $ext . ' 가 갈 폴더가 여러 곳입니다 ('
                   . implode('/ · ', array_keys($hit)) . '/). 그 주제의 [＋ 파일 넣기] 로 '
                   . '넣으십시오.');
    }
    return array('bad' => $base . ' — 갈 자리를 정할 수 없습니다. 그 주제의 '
               . '[＋ 파일 넣기] 로 넣거나, 폴더째면 ZIP 으로 올리십시오.');
}

/** 이름으로 자리를 정해 파일 하나를 넣는다. 갈음과 **같은 쓰기 경로**를 쓴다. */
function ex_deploy_add_one($target, $pd, $tmp, $up_name, $topic_key = '', $admin_id = '')
{
    $r = ex_deploy_add_rel($target, $pd, $up_name, $topic_key);
    if (isset($r['bad'])) return array('ok' => false, 'error' => $r['bad']);

    $out = ex_deploy_replace_one($target, $pd, $r['rel'], $tmp, $up_name, $admin_id);
    if (!empty($out['ok']) && empty($out['same'])) {
        $out['msg'] .= ' — ' . $r['why'];
    }
    return $out;
}
