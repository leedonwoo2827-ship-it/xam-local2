<?php
/**
 * 정적 파일 반입 — ZIP 하나를 브라우저로 올려 `/exam/pd/<pd>/` 에 넣는다.
 *
 * 이 화면이 있는 이유: FileZilla 를 시험운용자마다 줄 수 없다.
 * 문항은 이미 `adm/exam_import.php` 로 FTP 를 벗어났는데 정적 산출물은 아직 아니었다.
 *
 * 흐름:  XAM LOCAL 에서 빌드  →  06/pd/<pd>/ 를 ZIP  →  여기에 올림
 *        → ① 미리보기(쓰지 않는다)  → ② 반입
 *
 * ★ 상단은 **큰 주제 5개**다(문항 · 영상 링크 · 요약노트 · 문제 도식 · 공용 껍데기).
 *   파일 목록으로 보여주면 245개가 한 줄씩 뜨고 정작 알고 싶은 것("영상 링크는
 *   올라갔나?")이 그 안에 묻힌다. 사람이 하는 일은 파일 단위가 아니라 주제 단위다.
 *   각 박스가 **서버의 지금 상태**를 함께 보여준다 — FTP 는 「올렸다」를 기록하지
 *   않으므로 서버 파일을 직접 보는 것이 유일한 진실이다.
 *
 * ★ 미리보기와 반입이 나뉘어 있다. 245개를 올렸을 때 실제로 바뀐 것이 3개라는 사실이
 *   보여야 한다 — FTP 는 그것을 알려주지 않아서 "올렸는데 반영이 안 된다" 의 원인을
 *   늘 나중에 알았다.
 *
 * ★ 미리보기 뒤에 파일을 다시 골라야 하는 이유 — 브라우저는 폼이 새로 그려지면 고른
 *   파일을 잊는다. 서버에 임시로 두면 웹루트에 ZIP 이 남고(`/exam/` 아래면 그대로
 *   내려받힌다), 그 위험을 지지 않기로 했다. 관리자 토큰이 1회용이라 AJAX 로 두 번
 *   부르는 것도 안 된다(두 번째가 반드시 실패한다).
 *
 * 품목 링크: `exam_deploy.php?pd=<품목>` · 주제까지: `&topic=videos`
 *   `adm/seed_pd.php` 의 품목 표에서 바로 넘어온다.
 */
$sub_menu = '600800';
require_once './_common.php';

auth_check_menu($auth, $sub_menu, 'r');

require_once G5_ADMIN_PATH . '/exam_lib/deploy.php';

$TARGETS = ex_deploy_targets();
$TOPICS  = ex_deploy_topics();
$pd_list = ex_deploy_pd_list();

$topic_key = isset($_REQUEST['topic']) ? (string)$_REQUEST['topic'] : '';
$topic_sel = ex_deploy_topic($topic_key);

$target = isset($_REQUEST['target']) ? (string)$_REQUEST['target'] : '';
if ($target === '' && $topic_sel) $target = $topic_sel['target'];
if (!isset($TARGETS[$target])) $target = 'pd';

$pd = isset($_REQUEST['pd']) ? trim((string)$_REQUEST['pd']) : '';
if ($pd === '' && $pd_list) $pd = $pd_list[0]['pd_id'];

$rep    = null;      // 미리보기 또는 반입 결과
$did    = false;     // 실제로 썼는가
$fatal  = '';
$notice = '';

/**
 * 업로드 실패 문구. ZIP 통로와 낱개 갈음 통로가 **같은 표**를 쓴다 —
 * `exam_import.php` 와도 같은 표다. 같은 실수를 화면마다 다르게 설명할 이유가 없다.
 */
function exd_upload_err($f)
{
    $codes = array(
        UPLOAD_ERR_INI_SIZE   => 'php.ini 의 upload_max_filesize 를 초과했습니다.',
        UPLOAD_ERR_FORM_SIZE  => '폼 지정 크기를 초과했습니다.',
        UPLOAD_ERR_PARTIAL    => '파일이 일부만 전송됐습니다. 다시 시도하십시오.',
        UPLOAD_ERR_NO_FILE    => '파일을 고르지 않았습니다.',
        UPLOAD_ERR_NO_TMP_DIR => '서버에 임시 폴더가 없습니다.',
        UPLOAD_ERR_CANT_WRITE => '서버가 임시 파일을 쓰지 못했습니다.',
        UPLOAD_ERR_EXTENSION  => 'PHP 확장이 업로드를 막았습니다.',
    );
    $e = $f ? $f['error'] : UPLOAD_ERR_NO_FILE;
    // 빈 POST = post_max_size 초과. PHP 가 $_FILES 를 통째로 비운다.
    if ($e === UPLOAD_ERR_NO_FILE && empty($_POST)) {
        return 'post_max_size(' . ini_get('post_max_size') . ')를 초과해 요청이 통째로 '
             . '버려졌습니다. figs/ 만, 본문만 처럼 나눠 올리십시오.';
    }
    return isset($codes[$e]) ? $codes[$e] : '업로드 실패 (코드 ' . $e . ')';
}

/**
 * `$_FILES['x']` 를 **한 줄에 한 파일**인 목록으로 편다.
 *
 * `name="x[]"` 로 여러 개를 받으면 PHP 는 `name`·`tmp_name`·`error` 를 각각 배열로
 * 주는데(칸별 배열), 그 모양으로는 한 파일씩 다루는 코드를 쓸 수 없다.
 * 하나만 왔을 때도 같은 모양으로 돌려주므로 부르는 쪽은 개수를 신경 쓰지 않는다.
 */
function exd_files($key)
{
    if (!isset($_FILES[$key])) return array();
    $f = $_FILES[$key];
    if (!is_array($f['name'])) {
        return ($f['error'] === UPLOAD_ERR_NO_FILE && $f['name'] === '') ? array() : array($f);
    }
    $out = array();
    foreach (array_keys($f['name']) as $i) {
        if ($f['error'][$i] === UPLOAD_ERR_NO_FILE && $f['name'][$i] === '') continue;
        $out[] = array('name' => $f['name'][$i], 'tmp_name' => $f['tmp_name'][$i],
                       'error' => $f['error'][$i], 'size' => $f['size'][$i]);
    }
    return $out;
}

if ($_SERVER['REQUEST_METHOD'] === 'POST') {
    auth_check_menu($auth, $sub_menu, 'w');

    /* ★ check_token() 이 아니라 check_admin_token() 이다 — adm/admin.js 가 모든
     *   submit 을 가로채 ajax.token.php 의 관리자 토큰으로 이 필드를 덮어쓴다.
     *   `adm/exam_import.php` 가 같은 이유로 같은 것을 쓴다. */
    if (function_exists('check_admin_token')) {
        check_admin_token();
    } else {
        check_token();
    }

    $act = isset($_POST['act']) ? (string)$_POST['act'] : '';

    if ($act === 'orphan') {
        $e = ex_deploy_remove_orphan(isset($_POST['rel']) ? (string)$_POST['rel'] : '');
        if ($e === '') $notice = '잔존물을 지웠습니다.';
        else $fatal = $e;
    }
    /* 낱개 갈음 — 파일 하나, 또는 요약노트 과목 하나.
       ★ ZIP 통로와 같은 검증을 쓴다(`ex_deploy_replace_dest()` 안에서). 화면이 보낸
         `rel`·`href` 는 믿지 않고 **서버에 실제로 있는 것**과 대조한다. */
    elseif ($act === 'one') {
        $mode  = isset($_POST['mode']) ? (string)$_POST['mode'] : 'file';
        $topic = isset($_POST['topic']) ? (string)$_POST['topic'] : '';
        $ups   = exd_files('onefile');

        /* 「넣기」만 여러 개를 받는다. 갈음은 자리가 하나라 첫 파일만 쓴다. */
        if ($mode !== 'add') $ups = array_slice($ups, 0, 1);

        if (!$ups) {
            $fatal = exd_upload_err(null);
        } else {
            $good = array(); $bad = array();
            foreach ($ups as $u) {
                if ($u['error'] !== UPLOAD_ERR_OK) {
                    $bad[] = $u['name'] . ' — ' . exd_upload_err($u);
                    continue;
                }
                if ($mode === 'subject') {
                    $r = ex_deploy_theory_replace($pd, isset($_POST['href']) ? (string)$_POST['href'] : '',
                                                  $u['tmp_name'], $u['name'], $member['mb_id']);
                } elseif ($mode === 'add') {
                    $r = ex_deploy_add_one($target, $pd, $u['tmp_name'], $u['name'],
                                           $topic, $member['mb_id']);
                } else {
                    $r = ex_deploy_replace_one($target, $pd, isset($_POST['rel']) ? (string)$_POST['rel'] : '',
                                               $u['tmp_name'], $u['name'], $member['mb_id']);
                }
                @unlink($u['tmp_name']);
                if (!empty($r['ok'])) $good[] = $r['msg']; else $bad[] = $r['error'];
            }
            if ($good) $notice = implode("\n", $good);
            if ($bad)  $fatal  = implode("\n", $bad);
        }
    }
    /* 합본에 다시 이어붙이기 — 단위 파일만 올라가 「파일은 있는데 화면이 안 바뀐다」가
       된 상태의 복구다. 파일 업로드가 없다. */
    elseif ($act === 'stitch') {
        $r = ex_deploy_theory_restitch($pd, isset($_POST['href']) ? (string)$_POST['href'] : '',
                                      $member['mb_id']);
        if (!empty($r['ok'])) $notice = $r['msg'];
        else $fatal = $r['error'];
    }
    elseif ($act === 'inspect' || $act === 'apply') {
        $f = isset($_FILES['zipfile']) ? $_FILES['zipfile'] : null;

        if (!$f || $f['error'] !== UPLOAD_ERR_OK) {
            $fatal = exd_upload_err($f);
        } else {
            if ($act === 'apply') {
                $rep = ex_deploy_apply($f['tmp_name'], $target, $pd, $member['mb_id']);
                $did = true;
            } else {
                $rep = ex_deploy_inspect($f['tmp_name'], $target, $pd);
            }
            /* ★ 즉시 지운다 — 웹루트에 ZIP 이 남으면 그대로 내려받힌다.
                 `exam_import.php` 가 같은 이유로 같은 것을 한다. */
            @unlink($f['tmp_name']);
            if (!$rep['ok'] && $rep['error']) $fatal = $rep['error'];
        }
    }
}

$orphans = ex_deploy_orphans();

$g5['title'] = '정적 파일 반입';
require_once './admin.head.php';

function exd_h($s) { return htmlspecialchars((string)$s, ENT_QUOTES, 'UTF-8'); }
function exd_when($t) { return $t ? date('Y-m-d H:i', $t) : '-'; }

/** 서버에 있는 그 파일의 공개 주소. 내려받기 링크가 쓴다. */
function exd_url($target, $pd, $rel)
{
    return G5_URL . '/exam/' . ($target === 'shell' ? '' : 'pd/' . rawurlencode($pd) . '/')
         . str_replace('%2F', '/', rawurlencode($rel));
}

/**
 * 파일 한 줄 — 이름 · 크기 · 시각 · [갈음] [내려받기].
 *
 * ★ 갈음은 폼을 줄마다 두지 않는다. 도식이 479줄이라 폼이 479개 생긴다.
 *   버튼은 아래 공유 폼(`#exdOne`)의 숨은 값을 채우기만 한다.
 * ★ `.json` 은 내려받기를 걸지 않는다 — `/exam/.htaccess` 가 `.json` 직접 조회를
 *   403 으로 막는다(`videos.private.json` 에 정답 링크가 있어서 그렇게 뒀다).
 */
function exd_file_row($target, $pd, $rel, $bytes, $mtime)
{
    $json = (strtolower(pathinfo($rel, PATHINFO_EXTENSION)) === 'json');
    ?>
    <li>
      <span class="ok">&#10003;</span>
      <span class="fn"><?php echo exd_h($rel) ?></span>
      <span class="fsz"><?php echo exd_h(ex_deploy_kb($bytes)) ?></span>
      <span class="fdt"><?php echo $mtime ? exd_h(date('m-d H:i', $mtime)) : '-' ?></span>
      <span class="fac">
        <button type="button" class="rep" data-mode="file"
                data-target="<?php echo exd_h($target) ?>"
                data-rel="<?php echo exd_h($rel) ?>">갈음</button>
        <?php if ($json): ?>
          <span class="nodl" title="/exam/.htaccess 가 .json 직접 조회를 막습니다">내려받기 없음</span>
        <?php else: ?>
          <a class="dl" href="<?php echo exd_h(exd_url($target, $pd, $rel)) ?>"
             download target="_blank" rel="noopener">내려받기</a>
        <?php endif; ?>
      </span>
    </li>
    <?php
}
?>

<style>
.exdep{max-width:1000px}
.exdep .box{background:#fff;border:1px solid #e3e6ec;border-radius:8px;padding:20px 22px;margin:0 0 18px}
.exdep h2{font-size:15px;margin:0 0 12px;font-weight:700}
.exdep h3{font-size:13.5px;margin:18px 0 8px;font-weight:700;color:#333}
.exdep .hint{color:#666;font-size:13px;line-height:1.7}
.exdep code{background:#f4f5f7;padding:1px 5px;border-radius:3px;font-family:Consolas,monospace}
.exdep table.t{border-collapse:collapse;width:100%;margin:0 0 10px}
.exdep table.t th,.exdep table.t td{border:1px solid #e3e6ec;padding:7px 10px;text-align:left;font-size:13px}
.exdep table.t th{background:#f7f8fa;font-weight:600}
.exdep td.num{text-align:right;font-family:Consolas,monospace}
.exdep .n{font-weight:700;font-size:16px}
.exdep .ok{color:#0a7f3f}.exdep .warn{color:#b26a00}.exdep .bad{color:#c22638}.exdep .dim{color:#8a8f98}
.exdep .msg{padding:12px 16px;border-radius:6px;margin:0 0 16px;font-size:14px;line-height:1.7}
.exdep .msg.err{background:#fdeced;border:1px solid #c22638;color:#8c1220}
.exdep .msg.good{background:#e9f7ef;border:1px solid #0a7f3f;color:#075c2d}
.exdep .msg.info{background:#eef4fd;border:1px solid #3f6fb5;color:#1e3f70}

/* ── 큰 주제 — 배경 칠한 상자 하나 안에 작은 박스들이 가로로 ─────────────
   격자에 큰 카드를 깔면 한 화면에 두세 개만 보이고, 정작 알고 싶은 것("어디까지
   올라갔나")을 한눈에 못 본다. 주제가 5개뿐이라 한 줄에 늘어놓는 편이 낫다.
   바깥 상자에 배경을 칠하는 이유: 안의 흰 박스들이 「그 안에 든 것」으로 읽힌다. */
.exdep .tp-wrap{background:#f4f6f9;border:1px solid #dde1e8;border-radius:8px;
  padding:14px}
.exdep .tp-row{display:flex;flex-wrap:wrap;gap:10px}
.exdep .tp{flex:1 1 150px;max-width:220px;min-width:138px;text-align:left;
  border:1px solid #d3d8e0;border-radius:6px;background:#fff;padding:9px 11px 8px;
  cursor:pointer;font:inherit;transition:border-color .12s,box-shadow .12s}
.exdep .tp:hover{border-color:#3f6fb5;box-shadow:0 1px 4px rgba(63,111,181,.18)}
.exdep .tp.s-ok{border-top:3px solid #0a7f3f}
.exdep .tp.s-part{border-top:3px solid #b26a00}
.exdep .tp.s-none{border-top:3px solid #c8ccd4}
.exdep .tp-nm{display:flex;align-items:center;justify-content:space-between;gap:6px}
.exdep .tp-nm b{font-size:13.5px;color:#222}
.exdep .tp-mt{display:block;font-size:11px;color:#8a8f98;margin-top:3px;line-height:1.5}
.exdep .tp-imp{display:block;font-size:10.5px;color:#1e3f70;margin-top:3px}
.exdep .st{width:16px;height:16px;border-radius:50%;flex:none;display:inline-block;
  font-size:10px;line-height:16px;text-align:center;color:#fff;font-weight:700}
.exdep .st.ok{background:#0a7f3f}
.exdep .st.part{background:#b26a00}
.exdep .st.none{background:#c8ccd4;color:#6b7078}

/* ── 한패 표시 ──────────────────────────────────────────────────────────
   문항과 문제 도식은 **같이 올려야** 그림이 나온다. 문항(problems.js)이 도식을
   파일명으로 불러 쓰기 때문이다(빅분기 실측 167/235). 그래서 이 둘만 같은 색으로 둔다.
   요약노트는 그림을 HTML 안에 인라인으로 담아서 figs/ 를 쓰지 않는다 — 한패가 아니다.
   ★ 배경색 = 한패, 위쪽 색띠 = 상태. 두 축을 섞지 않는다. */
.exdep .tp.g-pair{background:#f2f8f4;border-color:#bcd9c7}
.exdep .tc.g-pair{background:#f2f8f4;border-color:#bcd9c7}
.exdep .pair-note{font-size:11.5px;color:#0a7f3f;margin:8px 0 0;display:flex;
  align-items:center;gap:6px}
.exdep .pair-note:before{content:'';width:9px;height:9px;border-radius:2px;
  background:#bcd9c7;border:1px solid #0a7f3f;flex:none}

/* 상세 — 여기도 박스다. 주제 하나가 박스 하나, 그 안에 파일이 한 줄씩. */
.exdep .tp-detail{margin-top:12px}
.exdep .tp-detail > summary{cursor:pointer;font-size:12.5px;color:#3f6fb5;
  font-weight:600;padding:4px 0;list-style:none}
.exdep .tp-detail > summary::-webkit-details-marker{display:none}
.exdep .tp-detail > summary:before{content:'\25be ';font-size:10px}
.exdep .tp-detail:not([open]) > summary:before{content:'\25b8 '}
.exdep .tp-cards{display:flex;flex-wrap:wrap;gap:10px;margin-top:8px}
.exdep .tc{flex:1 1 240px;min-width:220px;background:#fff;border:1px solid #d3d8e0;
  border-radius:6px;padding:10px 12px}
.exdep .tc-hd{font-size:12.5px;font-weight:700;color:#222;margin-bottom:6px;
  display:flex;justify-content:space-between;gap:6px;align-items:center}
.exdep .tc-fl{list-style:none;margin:0 0 7px;padding:0;font-size:11.5px;line-height:1.85}
.exdep .tc-fl li{display:flex;gap:5px;align-items:baseline}
.exdep .tc-fl .fn{font-family:Consolas,monospace;flex:1;word-break:break-all}
.exdep .tc-fl li.miss .fn{color:#b0b4bb}
.exdep .tc-fl li.optrow .fn{color:#9aa0a8}
.exdep .tc-nt{font-size:11.5px;color:#6b7078;line-height:1.6;margin:0;
  padding-top:7px;border-top:1px solid #eceff3}

.exdep .drop{margin:10px 0;padding:22px 14px;text-align:center;border:2px dashed #c8ccd4;
  border-radius:8px;background:#fafbfc;color:#767c86;font-size:13.5px;cursor:pointer}
.exdep .drop:hover{border-color:#3f6fb5;color:#1e3f70}
.exdep .drop.over{border-color:#3f6fb5;border-style:solid;background:#eef4fd;color:#1e3f70}
.exdep .drop b{display:block;font-size:14px;color:#333;margin-bottom:4px}
.exdep .rowsbox{max-height:340px;overflow:auto;border:1px solid #e3e6ec;border-radius:6px}
.exdep .rowsbox table.t{margin:0;border:0}
.exdep .steps{margin:0;padding:0;list-style:none;counter-reset:s}
.exdep .steps li{counter-increment:s;padding:7px 0 7px 30px;position:relative;font-size:13.5px;line-height:1.7}
.exdep .steps li:before{content:counter(s);position:absolute;left:0;top:7px;width:20px;height:20px;
  border-radius:50%;background:#3f6fb5;color:#fff;font-size:11px;font-weight:700;text-align:center;line-height:20px}
.exdep select,.exdep input[type=file]{font:inherit;padding:5px 7px;border:1px solid #ccc;border-radius:4px}
.exdep .lbl{display:block;margin:12px 0 4px;font-weight:600;font-size:13px}

/* ── 무엇이 올라가 있나 — 긴 박스 4개 ─────────────────────────────────────
   위 줄이 「어디까지 왔나」, 여기가 「그 안에 무엇이 있나」다. 위 박스와 1:1 이므로
   접힌 머리줄만 봐도 짝이 보인다. 공용 껍데기는 품목과 무관해서 이 줄에 두지 않는다.
   문제 도식이 혼자 479개까지 가므로 몸통은 스크롤 상자 + 걸러내기 칸이다. */
.exdep .accs{margin-top:12px;display:flex;flex-direction:column;gap:8px}
.exdep .acc{border:1px solid #d3d8e0;border-radius:6px;background:#fff}
.exdep .acc.g-pair{background:#f2f8f4;border-color:#bcd9c7}
.exdep .acc > summary{cursor:pointer;padding:9px 12px;display:flex;align-items:center;
  gap:9px;flex-wrap:wrap;list-style:none;font-size:12.5px}
.exdep .acc > summary::-webkit-details-marker{display:none}
.exdep .acc > summary:before{content:'\25b8';font-size:10px;color:#8a8f98;flex:none;width:9px}
.exdep .acc[open] > summary:before{content:'\25be'}
.exdep .acc > summary:hover{background:#f7f8fa}
.exdep .acc > summary b{font-size:13.5px;color:#222}
.exdep .acc-sp{flex:1}
.exdep .acc-bd{padding:0 12px 12px}
.exdep .fl{list-style:none;margin:0;padding:0;font-size:12px}
.exdep .fl li{display:flex;align-items:center;gap:8px;padding:4px 2px;
  border-bottom:1px solid #f2f4f7}
.exdep .fl li:last-child{border-bottom:0}
.exdep .fl .fn{font-family:Consolas,monospace;flex:1;word-break:break-all;color:#222}
.exdep .fl .fsz{width:66px;text-align:right;font-family:Consolas,monospace;color:#8a8f98;flex:none}
.exdep .fl .fdt{width:84px;color:#8a8f98;flex:none;font-size:11px}
.exdep .fl .fac{flex:none;white-space:nowrap;display:flex;gap:4px}
.exdep button.rep{font:inherit;font-size:11px;padding:2px 8px;border:1px solid #3f6fb5;
  border-radius:4px;background:#fff;color:#1e3f70;cursor:pointer}
.exdep button.rep:hover{background:#eef4fd}
.exdep a.dl{font:inherit;font-size:11px;padding:2px 8px;border:1px solid #d3d8e0;
  border-radius:4px;color:#6b7078;text-decoration:none}
.exdep a.dl:hover{border-color:#8a8f98;color:#333}
.exdep .nodl{font-size:11px;padding:2px 8px;color:#c0c4ca}
.exdep .flbox{max-height:320px;overflow:auto;border:1px solid #eceff3;border-radius:5px;
  padding:2px 9px;margin-top:9px}
.exdep .empty{margin-top:9px;padding:28px 12px;text-align:center;color:#9aa0a8;
  font-size:12.5px;border:1px dashed #d9dde3;border-radius:5px}
.exdep .filt{margin-top:9px;font:inherit;font-size:12px;padding:4px 8px;width:220px;
  border:1px solid #ccc;border-radius:4px}
.exdep .lblhd{font-size:11.5px;font-weight:700;color:#6b7078;margin:12px 0 1px}
.exdep .subj li{background:#fbfcfd}
.exdep .subj .fn{font-family:inherit;font-weight:600;color:#1c2530}
.exdep .unsync{font-size:11px;color:#b26a00;display:flex;align-items:center;gap:6px;
  padding:3px 2px 6px}

/* 판정 알약 — 408행이 쓰는데 정의가 없어 그동안 맨몸으로 나왔다. */
.exdep .chip{font-size:11.5px;padding:2px 8px;border-radius:10px;background:#f4f5f7;color:#555}
.exdep .chip.new{background:#e9f7ef;color:#075c2d}
.exdep .chip.replace{background:#fff4e5;color:#8a5200}
.exdep .chip.same{background:#f4f5f7;color:#8a8f98}

/* 갈아끼울 것을 고른 칸 — 고르기 전에는 숨는다 */
.exdep #exdOne{display:none}
.exdep #exdOne.on{display:block}
.exdep .firstup{margin-top:14px;background:#eef4fd;border:1px solid #cfe0f5;
  border-radius:6px;padding:12px 14px;font-size:13px;color:#1e3f70}
.exdep .firstup b{font-size:13.5px}
.exdep .tgt{font-family:Consolas,monospace;font-size:13px;background:#eef4fd;
  border:1px solid #cfe0f5;border-radius:5px;padding:9px 12px;margin:0 0 4px;color:#1e3f70}
</style>

<div class="exdep">

<?php if ($fatal): ?>
  <div class="msg err"><b>실패</b><br><?php echo nl2br(exd_h($fatal)) ?></div>
<?php endif; ?>
<?php if ($notice): ?>
  <div class="msg good"><?php echo nl2br(exd_h($notice)) ?></div>
<?php endif; ?>

<?php if (!$pd_list): ?>
  <div class="msg err">
    <b>등록된 품목이 없습니다.</b><br>
    먼저 <a href="seed_pd.php">품목 관리</a> 에서 품목 코드를 등록하십시오.
    <code>ex_product</code> 에 행이 없으면 문항 임포트도 막힙니다.
  </div>
<?php endif; ?>

<!-- ─────────────────────────────────────────────────────────────────────
     ① 큰 주제 5개 — 각 박스가 서버의 지금 상태를 함께 보여준다
     ────────────────────────────────────────────────────────────────── -->
<div class="box">
  <h2>여기 올리는 것 — 큰 주제 <?php echo count($TOPICS) ?>개</h2>
  <div class="hint" style="margin-bottom:12px">
    품목 <b><?php echo exd_h($pd) ?></b> 기준입니다. 각 박스의 상태는
    <b>서버 파일을 직접 본 것</b>입니다 — FTP 는 「올렸다」를 기록하지 않으므로
    서버에 묻는 것이 유일한 진실입니다. 아래에서 품목을 바꾸면 다시 셉니다.
  </div>

  <?php
  /* 상태를 한 번만 계산해 위 박스와 아래 상세가 같은 값을 쓴다. */
  $ST = array();
  foreach ($TOPICS as $t) $ST[$t['key']] = ex_deploy_topic_state($t, $pd);
  $CHIP = array('ok'   => array('ok', '&#10003;'),
                'part' => array('part', '!'),
                'none' => array('none', '&#183;'));

  /* 한패 — 같이 올려야 하는 주제. 문항이 도식을 불러 쓴다. */
  $PAIR = array('problems', 'figs');

  /* 서버에 **실제로** 있는 파일. 위 박스(선언된 항목의 상태)와 달리 이름까지 준다. */
  $FL = array();
  foreach ($TOPICS as $t) $FL[$t['key']] = ex_deploy_topic_files($t, $pd);

  /* 요약노트는 과목 줄이 먼저 온다 — 갈음의 단위가 파일이 아니라 과목이다. */
  $THY = ex_deploy_theory_index($pd);

  /* 긴 박스는 **품목 것만** 4개다. 공용 껍데기는 품목과 무관해서 따로 아래에 적는다. */
  $PDT = array(); $SHELL = null;
  foreach ($TOPICS as $t) {
      if ($t['target'] === 'shell') $SHELL = $t; else $PDT[] = $t;
  }
  ?>

  <div class="tp-wrap">
    <div class="tp-row">
      <?php foreach ($TOPICS as $t):
          $st = $ST[$t['key']];
          $c = $CHIP[$st['state']];
          $pair = in_array($t['key'], $PAIR, true); ?>
        <button type="button" class="tp<?php echo $pair ? ' g-pair' : '' ?> s-<?php
                echo exd_h($st['state']) ?> pick"
                data-target="<?php echo exd_h($t['target']) ?>"
                data-topic="<?php echo exd_h($t['key']) ?>"
                title="<?php echo exd_h($t['note']) ?>">
          <span class="tp-nm">
            <b><?php echo exd_h($t['label']) ?></b>
            <span class="st <?php echo exd_h($c[0]) ?>"><?php echo $c[1] ?></span>
          </span>
          <span class="tp-mt">
            <?php if ($st['bytes']): ?>
              <?php echo exd_h(ex_deploy_kb($st['bytes'])) ?> ·
              <?php echo exd_h(date('m-d H:i', $st['mtime'])) ?>
            <?php else: ?>
              서버에 없습니다
            <?php endif; ?>
          </span>
          <?php if ($st['missing']): ?>
            <span class="tp-mt" style="color:#b26a00">빠짐: <?php
              echo exd_h(ex_deploy_missing_text($st['missing'], 2)) ?></span>
          <?php endif; ?>
          <?php if ($t['import']): ?>
            <span class="tp-imp">＋ 문제 임포트</span>
          <?php endif; ?>
        </button>
      <?php endforeach; ?>
    </div>
    <p class="pair-note">색이 같은 둘은 <b>같이 올려야</b> 합니다 —
      문항이 도식을 불러 쓰므로 한쪽만 올리면 그림이 빈칸이 됩니다.</p>

    <!-- 무엇이 올라가 있나 — 긴 박스 4개. 위 줄과 1:1 이다.
         ★ 여기는 **서버에 실제로 있는 파일**만 적는다. 없는 파일을 줄로 늘어놓지
           않으므로, 아무것도 안 올라간 품목의 박스는 빈 박스가 된다(지금 sqld 의 문항).
           빠진 것은 위 박스가 「빠짐: problems.js」로 이미 말한다. -->
    <div class="accs">
      <?php foreach ($PDT as $t):
          $k  = $t['key'];
          $st = $ST[$k];
          $fl = $FL[$k];
          $c  = $CHIP[$st['state']];
          $subj = ($k === 'theory') ? $THY['rows'] : array();
          $n  = count($fl['rows']);
          $big = ($n > 30);   /* 도식만 여기 걸린다 — 걸러내기 칸을 준다 */
      ?>
        <details class="acc<?php echo in_array($k, $PAIR, true) ? ' g-pair' : '' ?>"
                 id="acc-<?php echo exd_h($k) ?>" data-topic="<?php echo exd_h($k) ?>">
          <summary>
            <b><?php echo exd_h($t['label']) ?></b>
            <span class="st <?php echo exd_h($c[0]) ?>"><?php echo $c[1] ?></span>
            <code><?php echo exd_h('/exam/pd/' . $pd . '/') ?></code>
            <span class="acc-sp"></span>
            <span class="dim"><?php if ($n): ?>
              <?php echo exd_h(ex_deploy_kb($fl['bytes'])) ?> ·
              <?php echo exd_h(date('m-d H:i', $fl['mtime'])) ?> ·
              파일 <?php echo $n + $fl['cut'] ?>개<?php
                if ($subj): ?> · 과목 <?php echo count($subj) ?>개<?php endif;
            else: ?>서버에 없습니다<?php endif; ?></span>
          </summary>
          <div class="acc-bd">

            <?php /* ── 요약노트 — 과목 줄이 먼저다. 갈음의 단위가 파일이 아니라 과목이다. */ ?>
            <?php if ($k === 'theory' && $subj): ?>
              <p class="lblhd">과목 — 하나씩 갈아끼웁니다</p>
              <ul class="fl subj">
                <?php foreach ($subj as $s): ?>
                  <li>
                    <span class="<?php echo $s['in_content'] ? 'ok' : 'warn' ?>"><?php
                      echo $s['in_content'] ? '&#10003;' : '!' ?></span>
                    <span class="fn"><?php echo exd_h($s['label']) ?><?php
                      if (!$s['vid']): ?> <span class="dim"
                        style="font-weight:400">강의 링크 없음</span><?php endif; ?></span>
                    <span class="fsz"><?php echo exd_h(ex_deploy_kb($s['body_bytes'])) ?></span>
                    <span class="fdt"><?php echo $s['unit_mtime']
                      ? exd_h(date('m-d H:i', $s['unit_mtime'])) : '-' ?></span>
                    <span class="fac">
                      <button type="button" class="rep" data-mode="subject"
                              data-href="<?php echo exd_h($s['href']) ?>"
                              data-label="<?php echo exd_h($s['label']) ?>">갈음</button>
                      <?php if ($s['unit_ok']): ?>
                        <a class="dl" href="<?php echo exd_h(exd_url('pd', $pd, $s['unit_rel'])) ?>"
                           download target="_blank" rel="noopener">내려받기</a>
                      <?php else: ?>
                        <span class="nodl" title="갈아끼우면 단위 파일이 생깁니다">단위 파일 없음</span>
                      <?php endif; ?>
                    </span>
                  </li>
                  <?php if (!$s['synced']): ?>
                    <li class="unsync">
                      <span>이 과목의 단위 파일과 합본(<code>theory_content.js</code>)이
                        다릅니다 — 화면에는 합본이 나오므로 아직 안 바뀐 상태입니다.</span>
                      <form method="post" style="display:inline">
                        <input type="hidden" name="token" value="">
                        <input type="hidden" name="act" value="stitch">
                        <input type="hidden" name="href" value="<?php echo exd_h($s['href']) ?>">
                        <input type="hidden" name="target" value="pd">
                        <input type="hidden" name="pd" value="<?php echo exd_h($pd) ?>">
                        <input type="submit" value="다시 이어붙이기" class="btn_submit">
                      </form>
                    </li>
                  <?php endif; ?>
                <?php endforeach; ?>
              </ul>
              <?php if ($THY['old']): ?>
                <div class="msg info" style="margin:9px 0 0">
                  서버의 <code>theory_content.js</code> 가 <b>옛 한 덩이 형식</b>입니다 —
                  과목별로 갈려면 새로 빌드한 것을 ZIP 으로 한 번 올려 형식을 바꾸십시오.
                  그 뒤로는 과목 하나씩 됩니다.
                </div>
              <?php endif; ?>
              <p class="lblhd">파일</p>
            <?php endif; ?>

            <?php /* ── 파일 줄 */ ?>
            <?php if (!$n): ?>
              <div class="empty">서버에 아무것도 없습니다.<br>
                <span style="font-size:11.5px">아래 <b>ZIP 올리기</b> 로 이 주제를 처음 올립니다.</span>
              </div>
            <?php else: ?>
              <?php if ($big): ?>
                <input type="text" class="filt" placeholder="파일 이름으로 걸러내기 (<?php
                  echo $n ?>개)">
              <?php endif; ?>
              <div class="flbox">
                <ul class="fl">
                  <?php foreach ($fl['rows'] as $r)
                          exd_file_row($t['target'], $pd, $r['rel'], $r['bytes'], $r['mtime']); ?>
                </ul>
              </div>
              <?php if ($fl['cut']): ?>
                <p class="hint" style="color:#b26a00;font-size:11.5px;margin:6px 0 0">
                  ★ <?php echo (int)$fl['cut'] ?>개는 목록에서 뺐습니다 —
                  한 번에 <?php echo EX_DEPLOY_MAX_ENTRIES ?>줄까지만 그립니다.
                  낱개로 갈 것이 아니면 ZIP 으로 올리십시오.
                </p>
              <?php endif; ?>
            <?php endif; ?>

            <p class="tc-nt" style="margin-top:10px"><?php echo exd_h($t['note']) ?></p>
            <p style="margin:8px 0 0;display:flex;gap:6px;flex-wrap:wrap">
              <button type="button" class="rep" data-mode="add"
                      data-target="<?php echo exd_h($t['target']) ?>"
                      data-topic="<?php echo exd_h($k) ?>"
                      data-label="<?php echo exd_h($t['label']) ?>">＋ 파일 넣기</button>
              <button type="button" class="rep zipgo" data-target="<?php
                echo exd_h($t['target']) ?>">ZIP 으로 올리기</button>
            </p>
          </div>
        </details>
      <?php endforeach; ?>
    </div>
  </div>

  <?php /* ── 공용 껍데기 — 품목과 무관해서 위 줄에 두지 않는다. 내역만 쭈욱 적는다. */ ?>
  <?php if ($SHELL): $fl = $FL[$SHELL['key']]; $c = $CHIP[$ST[$SHELL['key']]['state']]; ?>
    <h3><?php echo exd_h($SHELL['label']) ?>
      <span class="st <?php echo exd_h($c[0]) ?>"><?php echo $c[1] ?></span>
      <code style="font-weight:400"><?php echo exd_h('/exam/') ?></code>
      <span class="dim" style="font-weight:400;font-size:11.5px">
        <?php echo count($fl['rows']) ?>개 · <?php echo exd_h(ex_deploy_kb($fl['bytes'])) ?>
      </span>
    </h3>
    <div class="hint" style="margin-bottom:6px">
      모든 문제집이 <b>함께</b> 씁니다 — 여기 있는 파일을 갈면 다른 문제집 화면도 같이
      바뀝니다. 품목을 바꿔도 이 목록은 그대로입니다.
    </div>
    <?php if (!$fl['rows']): ?>
      <div class="empty">서버에 아무것도 없습니다.</div>
    <?php else: ?>
      <div class="flbox">
        <ul class="fl">
          <?php foreach ($fl['rows'] as $r)
                  exd_file_row('shell', $pd, $r['rel'], $r['bytes'], $r['mtime']); ?>
        </ul>
      </div>
    <?php endif; ?>
    <p style="margin:8px 0 0;display:flex;gap:6px;flex-wrap:wrap">
      <button type="button" class="rep" data-mode="add" data-target="shell"
              data-topic="<?php echo exd_h($SHELL['key']) ?>"
              data-label="<?php echo exd_h($SHELL['label']) ?>">＋ 파일 넣기</button>
      <button type="button" class="rep zipgo" data-target="shell">ZIP 으로 올리기</button>
    </p>
    <p class="tc-nt" style="margin-top:8px"><?php echo exd_h($SHELL['note']) ?></p>
  <?php endif; ?>

  <?php /* ── 만든 것 그대로 올리기 — 처음 올릴 때의 정문.
           빌드가 `06/_올릴것/` 에 모아둔 것을 통째로 골라 떨어뜨리면, 파일 이름만
           보고 각자 갈 자리로 흩어진다(`ex_deploy_add_rel()`). 폴더가 끼는 것
           (도식 479개 · assets/)만 ZIP 이고 나머지는 파일 그대로다. */ ?>
  <div class="firstup">
    <b>처음 올리기 — 만든 것을 그대로 떨어뜨리십시오</b>
    <p class="hint" style="margin:6px 0 0">
      빌드가 <code>06/_올릴것/</code> 에 모아둡니다. 그 안의 <b>파일을 전부 골라</b>
      여기에 놓으면 이름을 보고 제 자리로 갑니다 —
      <code>problems.js</code>·<code>videos.js</code>·<code>theory*.js</code> 는 뿌리로,
      <code>summary_*.js</code> 는 <code>theory/</code> 로, <code>.svg</code> 는
      <code>figs/</code> 로. <b>ZIP 은 따로</b> 올리십시오(<code>문제도식.zip</code> ·
      <code>공용껍데기.zip</code>) — 폴더가 끼는 것은 그쪽이 빠릅니다.
    </p>
    <p style="margin:9px 0 0;display:flex;gap:6px;flex-wrap:wrap">
      <button type="button" class="rep" data-mode="add" data-target="pd" data-topic=""
              data-label="품목 콘텐츠 — 만든 것 그대로">＋ 품목 파일 넣기</button>
      <button type="button" class="rep" data-mode="add" data-target="shell" data-topic=""
              data-label="공용 껍데기 — 만든 것 그대로">＋ 껍데기 파일 넣기</button>
      <button type="button" class="rep zipgo" data-target="pd">ZIP 올리기로</button>
    </p>
  </div>

  <div class="hint" style="margin-top:14px">
    <b>받지 않는 것</b><br>
    · <code>.php</code> — <code>/exam/brand.php</code> 가 같은 폴더에 있습니다. PHP 를 받는
      통로를 열면 그건 서버에서 임의 코드를 실행하는 경로가 됩니다. <b>FTP 로 올리십시오.</b>
      (테마·스킨·<code>api/</code>·<code>adm/</code> 도 같습니다 — 사이트 구조를 바꿀 때만
      바뀌므로 자동화 대상에서 뺐습니다.)<br>
    · <code>problems.json</code> — 파일로 두는 것이 아니라
      <a href="exam_import.php">문제 임포트</a> 화면으로 DB 에 넣습니다.
      <code>/exam/.htaccess</code> 가 <code>.json</code> 직접 조회를 막는 이유도 그것입니다.<br>
    · <code>.mp4</code> — 영상은 구글 드라이브·유튜브로 갑니다. 링크만
      <code>videos.js</code> 에 실려 여기로 옵니다.
  </div>
</div>

<!-- ─────────────────────────────────────────────────────────────────────
     ①-2 낱개 갈음 — 위 목록에서 [갈음] 을 누르면 여기가 열린다

     ★ 폼을 **하나만** 둔다. 줄마다 폼을 두면 도식에서 479개가 생긴다.
     ★ 미리보기가 없다. 파일 하나는 「무엇이 바뀌는지」가 이미 그 줄에 다 보이고,
       내용이 같으면 서버가 쓰지 않고 「이미 같음」으로 돌려준다.
     ★ AJAX 를 쓰지 않는다 — 관리자 토큰이 1회용이라 두 번째 호출이 반드시 실패한다.
       `adm/admin.js` 가 **submit 버튼 클릭**을 가로채 토큰을 채우므로, 사람이 아래
       버튼을 누르는 평범한 폼 제출이어야 한다.
     ────────────────────────────────────────────────────────────────── -->
<div class="box" id="exdOne">
  <h2>갈아끼우기 — 고른 것 하나만</h2>
  <form method="post" enctype="multipart/form-data" id="exdOneForm">
    <input type="hidden" name="token" value="">
    <input type="hidden" name="act" value="one">
    <input type="hidden" name="mode" value="file" id="exdOneMode">
    <input type="hidden" name="target" value="pd" id="exdOneTarget">
    <input type="hidden" name="pd" value="<?php echo exd_h($pd) ?>">
    <input type="hidden" name="rel" value="" id="exdOneRel">
    <input type="hidden" name="href" value="" id="exdOneHref">
    <input type="hidden" name="topic" value="" id="exdOneTopic">

    <p class="tgt" id="exdOneTgt">고른 것이 없습니다</p>
    <div class="hint" id="exdOneNote" style="margin-bottom:8px"></div>

    <div class="drop" id="exdOneDrop">
      <b>갈아끼울 파일을 여기에 끌어다 놓으십시오</b>
      눌러서 고르셔도 됩니다 · <span id="exdOneName" class="dim">고른 파일 없음</span>
    </div>
    <input type="file" name="onefile[]" id="exdOneFile" multiple style="display:none">

    <p style="margin-top:12px">
      <input type="submit" value="갈아끼우기" class="btn_submit" onclick="return exdOneGo()">
      &nbsp;
      <button type="button" class="rep" id="exdOneCancel">그만두기</button>
    </p>
  </form>
</div>

<!-- ─────────────────────────────────────────────────────────────────────
     ② 결과 — 미리보기 또는 반입
     ────────────────────────────────────────────────────────────────── -->
<?php if ($rep && $rep['ok']): ?>
  <div class="box" id="exdResult">
    <h2><?php echo $did ? '반입 결과' : '미리보기 — 아직 아무것도 쓰지 않았습니다' ?></h2>

    <?php if ($did): ?>
      <div class="msg good">
        <b><?php echo (int)$rep['written'] ?>개 썼습니다.</b>
        이미 같아서 건드리지 않은 것 <?php echo (int)$rep['skipped'] ?>개.
        <?php if ($rep['failed']): ?>
          <span class="bad">실패 <?php echo count($rep['failed']) ?>개.</span>
        <?php endif; ?>
        <br><span class="dim">
          <code><?php echo exd_h($rep['server']) ?></code> ·
          <code>ex_log</code> 에 <code>deploy</code> 로 기록했습니다.
        </span>
      </div>
      <?php if ($rep['failed']): ?>
        <div class="msg err"><b>쓰지 못한 것</b>
          <?php foreach (array_slice($rep['failed'], 0, 20) as $x): ?>
            <br><?php echo exd_h($x) ?>
          <?php endforeach; ?>
        </div>
      <?php endif; ?>
    <?php else: ?>
      <div class="msg info">
        <b>확인하고 아래에서 같은 파일을 다시 골라 [반입] 하십시오.</b><br>
        <span class="dim">브라우저는 페이지가 새로 그려지면 고른 파일을 잊습니다.
        서버에 임시로 두면 웹루트에 ZIP 이 남아 그대로 내려받히므로 그렇게 하지 않았습니다.</span>
      </div>
    <?php endif; ?>

    <table class="t">
      <tr>
        <th style="width:130px">새로 생김</th>
        <th style="width:130px">갈아끼움</th>
        <th style="width:130px">이미 같음</th>
        <th>합계</th>
      </tr>
      <tr>
        <td class="n ok"><?php echo (int)$rep['counts']['new'] ?></td>
        <td class="n warn"><?php echo (int)$rep['counts']['replace'] ?></td>
        <td class="n dim"><?php echo (int)$rep['counts']['same'] ?></td>
        <td class="hint">
          항목 <?php echo count($rep['rows']) ?>개 ·
          <?php echo exd_h(ex_deploy_kb($rep['total_bytes'])) ?> ·
          대상 <code><?php echo exd_h($rep['server']) ?></code>
        </td>
      </tr>
    </table>

    <?php if ($rep['rejected']): ?>
      <div class="msg err">
        <b>받지 않은 것 <?php echo count($rep['rejected']) ?>개</b>
        <?php foreach (array_slice($rep['rejected'], 0, 20) as $x): ?>
          <br><code><?php echo exd_h($x['name']) ?></code> — <?php echo exd_h($x['why']) ?>
        <?php endforeach; ?>
        <?php if (count($rep['rejected']) > 20): ?>
          <br>… 외 <?php echo count($rep['rejected']) - 20 ?>개
        <?php endif; ?>
      </div>
    <?php endif; ?>

    <h3>파일별 판정</h3>
    <div class="rowsbox">
      <table class="t">
        <tr><th>파일</th><th style="width:90px">크기</th><th style="width:100px">판정</th></tr>
        <?php foreach ($rep['rows'] as $r): ?>
          <tr>
            <td><code><?php echo exd_h($r['rel']) ?></code></td>
            <td class="num"><?php echo exd_h(ex_deploy_kb($r['bytes'])) ?></td>
            <td><span class="chip <?php echo exd_h($r['verdict']) ?>"><?php
              echo $r['verdict'] === 'new' ? '새로 생김'
                 : ($r['verdict'] === 'replace' ? '갈아끼움' : '이미 같음') ?></span></td>
          </tr>
        <?php endforeach; ?>
      </table>
    </div>
    <div class="hint">
      「이미 같음」은 <b>건드리지 않습니다</b> — 파일 시각이 바뀌면
      <code>check.php</code> 의 캐시 무효화가 헛돌고, 무엇이 실제로 바뀌었는지도
      서버에서 알 수 없게 됩니다.
    </div>
  </div>
<?php endif; ?>

<!-- ─────────────────────────────────────────────────────────────────────
     ③ 올리는 칸
     ────────────────────────────────────────────────────────────────── -->
<div class="box" id="exdUpload">
  <h2>ZIP 올리기</h2>
  <form method="post" enctype="multipart/form-data" id="exdForm">
    <?php /* value 를 비워둔다 — adm/admin.js 가 submit 직전에 관리자 토큰으로 채운다. */ ?>
    <input type="hidden" name="token" value="">
    <input type="hidden" name="act" value="inspect" id="exdAct">

    <label class="lbl">대상</label>
    <select name="target" id="exdTarget">
      <?php foreach ($TARGETS as $k => $t): ?>
        <option value="<?php echo exd_h($k) ?>" <?php echo $target === $k ? 'selected' : '' ?>>
          <?php echo exd_h($t['label']) ?> — <?php echo exd_h($t['server']) ?>
        </option>
      <?php endforeach; ?>
    </select>

    <label class="lbl">품목</label>
    <select name="pd" id="exdPd" onchange="this.form.action='';location.href='exam_deploy.php?pd='+encodeURIComponent(this.value)">
      <?php foreach ($pd_list as $p): ?>
        <option value="<?php echo exd_h($p['pd_id']) ?>" <?php echo $pd === $p['pd_id'] ? 'selected' : '' ?>>
          <?php echo exd_h($p['pd_id']) ?> — <?php echo exd_h($p['pd_name']) ?><?php
            echo $p['pd_open'] ? '' : ' (숨김)' ?>
        </option>
      <?php endforeach; ?>
    </select>
    <div class="hint">품목을 바꾸면 위 박스의 상태를 다시 셉니다.
      공용 껍데기는 품목과 무관합니다 — <code>detail.html</code> 한 장이
      <code>?pd=</code> 로 모든 문제집을 렌더합니다.</div>

    <div class="drop" id="exdDrop">
      <b>ZIP 을 여기에 끌어다 놓으십시오</b>
      눌러서 고르셔도 됩니다 · <span id="exdName" class="dim">고른 파일 없음</span>
    </div>
    <input type="file" name="zipfile" id="exdFile" accept=".zip,application/zip" style="display:none">

    <p style="margin-top:14px">
      <input type="submit" value="① 미리보기 (쓰지 않습니다)" class="btn_submit"
             onclick="document.getElementById('exdAct').value='inspect'">
      &nbsp;
      <input type="submit" value="② 반입 실행" class="btn_submit"
             onclick="return exdApply()">
    </p>
  </form>
  <div class="hint">
    서버 상한: <code>upload_max_filesize <?php echo exd_h(ini_get('upload_max_filesize')) ?></code> ·
    <code>post_max_size <?php echo exd_h(ini_get('post_max_size')) ?></code> ·
    <code>max_execution_time <?php echo exd_h(ini_get('max_execution_time')) ?>초</code>
    <?php if (!class_exists('ZipArchive')): ?>
      <br><span class="bad"><b>ZipArchive 확장이 없습니다</b> — 이 화면은 동작하지 않습니다.
      호스팅에 문의하거나 FTP 로 올리십시오.</span>
    <?php endif; ?>
    <br>항목 상한 <?php echo EX_DEPLOY_MAX_ENTRIES ?>개 ·
    압축 풀린 합계 <?php echo exd_h(ex_deploy_kb(EX_DEPLOY_MAX_TOTAL)) ?>.
    시간(<?php echo exd_h(ini_get('max_execution_time')) ?>초)이 실제 제약이라
    넘으면 <code>figs/</code> 만, 본문만 처럼 나눠 올립니다.
  </div>
</div>

<!-- ─────────────────────────────────────────────────────────────────────
     ④ 잔존물 — FTP 가 남긴 옛 납작 사본
     ────────────────────────────────────────────────────────────────── -->
<?php if ($orphans): ?>
  <div class="box">
    <h2 class="bad">옛 납작 사본이 서버에 남아 있습니다</h2>
    <div class="hint">
      예전 빌드는 <code>06/</code> 루트에 납작하게 만들어 <code>/exam/problems.js</code> 로
      올라갔습니다. 그 뒤 품목별 <code>pd/&lt;pd&gt;/</code> 로 내렸지만
      <b>FTP 는 지우지 않으므로</b> 옛 파일이 그대로 남습니다.
      두 번째 문제집이 첫 번째를 덮어쓰던 그 구조의 잔재이고,
      <code>axexam/scripts/deploy_check.py</code> 도 같은 것을 경고합니다.
    </div>
    <table class="t" style="margin-top:10px">
      <tr><th>파일</th><th style="width:90px">크기</th><th style="width:150px">서버 시각</th>
          <th style="width:110px"></th></tr>
      <?php foreach ($orphans as $o): ?>
        <tr>
          <td><code>/exam/<?php echo exd_h($o['rel']) ?></code>
            <?php if (isset($o['files'])): ?>
              <span class="dim"><?php echo (int)$o['files'] ?>개</span>
            <?php endif; ?></td>
          <td class="num"><?php echo $o['bytes'] ? exd_h(ex_deploy_kb($o['bytes'])) : '-' ?></td>
          <td class="dim"><?php echo exd_h(exd_when($o['mtime'])) ?></td>
          <td>
            <?php if (substr($o['rel'], -1) === '/'): ?>
              <span class="dim">FTP 로 확인</span>
            <?php else: ?>
              <form method="post" style="display:inline"
                    onsubmit="return confirm('/exam/<?php echo exd_h($o['rel']) ?> 를 지웁니다. 되돌릴 수 없습니다.')">
                <input type="hidden" name="token" value="">
                <input type="hidden" name="act" value="orphan">
                <input type="hidden" name="rel" value="<?php echo exd_h($o['rel']) ?>">
                <input type="hidden" name="target" value="<?php echo exd_h($target) ?>">
                <input type="hidden" name="pd" value="<?php echo exd_h($pd) ?>">
                <input type="submit" value="지우기" class="btn_submit">
              </form>
            <?php endif; ?>
          </td>
        </tr>
      <?php endforeach; ?>
    </table>
  </div>
<?php endif; ?>

<!-- ─────────────────────────────────────────────────────────────────────
     ⑤ 만드는 법
     ────────────────────────────────────────────────────────────────── -->
<div class="box">
  <h2>운영 순서 — 세 단계뿐입니다</h2>
  <ol class="steps">
    <li><b>처음 올릴 때 — 만든 것을 그대로 올립니다.</b><br>
      XAM LOCAL 에서 <b>빌드 실행</b> → <code>06/_올릴것/</code> 이 생깁니다.
      빌드가 <b>올릴 것만</b> 그 폴더에 모아 둡니다 — 폴더가 끼는 것
      (<code>문제도식.zip</code> · <code>공용껍데기.zip</code>)은 미리 압축해 두고
      나머지는 파일 그대로입니다.<br>
      <span class="dim">그 폴더의 <b>파일을 전부 골라</b> 위 [＋ 품목 파일 넣기] 에 놓으면
      이름을 보고 각자 갈 자리로 갑니다(<code>summary_*.js</code> 는
      <code>theory/</code> 로, <code>.svg</code> 는 <code>figs/</code> 로).
      ZIP 두 개는 아래 <b>ZIP 올리기</b> 에서 하나씩. 같은 내용이
      <code>올리는순서.txt</code> 에도 적혀 있습니다.</span></li>

    <li><b>올라가면 목록이 생깁니다.</b><br>
      올리기 전에는 주제 박스가 <b>빈 박스</b>입니다 — 서버에 없는 파일을 줄로
      늘어놓지 않기 때문입니다. 올라간 것부터 줄로 뜨고, 그 줄이 곧
      <b>수험생 화면에 나가는 것</b>입니다.<br>
      <span class="dim">여기 없으면 사이트에도 없고, 그 반대도 없습니다 — FTP 는
      「올렸다」를 기록하지 않으므로 서버 파일을 직접 본 것이 유일한 진실입니다.</span></li>

    <li><b>나중에 한 군데를 고칠 때 — 그 줄만 갈아끼웁니다.</b><br>
      고칠 줄의 <b>[내려받기]</b> 로 지금 서버에 있는 것을 받아, 로컬에서 그 단위만
      고쳐 만든 뒤 같은 줄의 <b>[갈음]</b> 으로 올립니다.<br>
      <span class="dim">요약노트는 단위가 <b>과목</b>입니다 — 한 과목을 갈아도 나머지
      과목은 서버 것이 그대로 남습니다. 내용이 이미 같으면 쓰지 않습니다(파일 시각이
      바뀌면 <code>check.php</code> 의 캐시 무효화가 헛돕니다).</span></li>

    <li><b>문항을 고쳤다면 임포트를 함께 합니다.</b><br>
      <a href="exam_import.php">문제 임포트</a> 로 <code>problems.json</code> 을 올립니다.
      <span class="dim">그건 파일이 아니라 DB 입니다. 서버에서는 DB 가 이기고
      <code>problems.js</code> 는 정적 폴백이라 <b>둘 다</b> 해야 화면이 맞습니다.</span></li>
  </ol>
  <div class="hint" style="margin-top:4px">
    <b>ZIP 은 둘뿐입니다</b> — <code>figs/</code> 는 479개까지 가고
    <code>assets/</code> 도 여러 개입니다. 낱개로 올리면 서버 실행 시간
    (<code><?php echo exd_h(ini_get('max_execution_time')) ?>초</code>)에 걸리므로 이 둘만
    압축합니다. 빌드가 미리 만들어 두므로 손으로 압축할 일은 없습니다.
    <code>공용껍데기.zip</code> 은 아래에서 <b>대상</b>을 「공용 껍데기」로 바꿔 올리십시오.
  </div>
  <h3>무엇을 고쳤을 때 무엇만 갈면 되는가</h3>
  <table class="t">
    <tr><th style="width:210px">고친 것</th><th>주제</th><th>파일</th><th style="width:100px">임포트</th></tr>
    <tr><td>영상 링크만</td><td>해설 영상 링크</td>
        <td><code>videos.js</code> <span class="dim">(레벨 제한이 있으면
            <code>videos.private.json</code>)</span></td>
        <td class="dim">필요 없음</td></tr>
    <tr><td>이론 강의 링크</td><td>요약노트</td><td><code>theory.js</code></td>
        <td class="dim">필요 없음</td></tr>
    <tr><td>요약노트 본문</td><td>요약노트</td>
        <td><code>theory_content.js</code> · <code>theory/</code></td>
        <td class="dim">필요 없음</td></tr>
    <tr><td>문항 내용</td><td>문항</td><td><code>problems.js</code></td>
        <td class="warn"><b>필요</b></td></tr>
    <tr><td>문제 그림</td><td>문제 도식</td><td><code>figs/</code></td>
        <td class="dim">필요 없음</td></tr>
    <tr><td>사이트 구조·PHP</td><td>공용 껍데기</td>
        <td><code>.html</code>·<code>assets/</code> 는 여기서,
            <code>.php</code> 는 <span class="dim">FTP</span></td>
        <td class="dim">-</td></tr>
  </table>
  <div class="hint">
    <code>videos.private.json</code> 은 <code>api/videos.php</code> 가 요청마다 다시 읽습니다 —
    캐시도 DB도 없어서 <b>그 한 파일만 올리면 즉시 반영</b>됩니다.
    <code>problems.js</code>·<code>theory_content.js</code>·<code>figs/</code> 는
    <code>/exam/.htaccess</code> 의 1시간 캐시를 지납니다.
  </div>
</div>

</div>

<script>
/* 드래그드랍 — 고른 파일을 숨은 input 에 넣고 평소 폼 제출로 보낸다.
   AJAX 를 쓰지 않는 이유: 관리자 토큰(check_admin_token)은 1회용이라 두 번 부르면
   두 번째가 반드시 실패한다. adm/admin.js 가 폼 제출에는 토큰을 알아서 채운다. */
(function () {
  var drop = document.getElementById('exdDrop');
  var file = document.getElementById('exdFile');
  var name = document.getElementById('exdName');
  var tsel = document.getElementById('exdTarget');
  if (!drop || !file) return;

  function show() {
    var f = file.files && file.files[0];
    name.textContent = f ? (f.name + ' · ' + Math.round(f.size / 1024) + 'KB') : '고른 파일 없음';
    name.className = f ? '' : 'dim';
  }
  drop.addEventListener('click', function () { file.click(); });
  file.addEventListener('change', show);
  drop.addEventListener('dragover', function (e) {
    e.preventDefault(); drop.className = 'drop over';
  });
  drop.addEventListener('dragleave', function () { drop.className = 'drop'; });
  drop.addEventListener('drop', function (e) {
    e.preventDefault(); drop.className = 'drop';
    if (!e.dataTransfer || !e.dataTransfer.files || !e.dataTransfer.files.length) return;
    /* DataTransfer 를 input.files 에 그대로 넣는다 — 폼 제출로 올라간다. */
    try { file.files = e.dataTransfer.files; } catch (err) {
      alert('이 브라우저는 끌어다 놓기를 지원하지 않습니다. 눌러서 고르십시오.');
      return;
    }
    show();
  });

  /* 위 주제 박스 → **대응하는 긴 박스를 펼치고 거기로 내려간다.**
     예전에는 파일 선택창을 바로 열었는데, 무엇을 올리는 자리인지 보기도 전에 창이 떠서
     놀랍다. 「어디까지 왔나」를 누르면 「그 안에 무엇이 있나」로 가는 것이 자연스럽다. */
  var picks = document.querySelectorAll('.exdep button.pick');
  for (var i = 0; i < picks.length; i++) {
    picks[i].addEventListener('click', function () {
      var k = this.getAttribute('data-topic');
      var acc = k ? document.getElementById('acc-' + k) : null;
      if (acc) {
        acc.open = true;
        if (acc.scrollIntoView) acc.scrollIntoView({ behavior: 'smooth', block: 'center' });
        return;
      }
      /* 공용 껍데기는 긴 박스가 없다(품목과 무관해서 아래에 따로 적는다) — ZIP 칸으로. */
      if (tsel) tsel.value = this.getAttribute('data-target');
      var box = document.getElementById('exdUpload');
      if (box && box.scrollIntoView) box.scrollIntoView({ behavior: 'smooth', block: 'start' });
    });
  }

  /* [이 주제 ZIP 으로 올리기] — 대상을 맞추고 ③ 으로 내려간다. ZIP 을 주제별로
     만드는 것은 사람이 한다(폴더에서 그 파일만 골라 압축). */
  var zips = document.querySelectorAll('.exdep button.zipgo');
  for (var z = 0; z < zips.length; z++) {
    zips[z].addEventListener('click', function () {
      if (tsel) tsel.value = this.getAttribute('data-target');
      var box = document.getElementById('exdUpload');
      if (box && box.scrollIntoView) box.scrollIntoView({ behavior: 'smooth', block: 'start' });
    });
  }

  /* 걸러내기 — 도식이 479줄이라 눈으로 찾을 수 없다. 줄을 숨기기만 한다. */
  var filts = document.querySelectorAll('.exdep input.filt');
  for (var fi = 0; fi < filts.length; fi++) {
    filts[fi].addEventListener('input', function () {
      var q = this.value.toLowerCase();
      var box = this.parentNode.querySelector('.flbox');
      if (!box) return;
      var li = box.querySelectorAll('li');
      var shown = 0;
      for (var j = 0; j < li.length; j++) {
        var nm = li[j].querySelector('.fn');
        var hit = !q || (nm && nm.textContent.toLowerCase().indexOf(q) >= 0);
        li[j].style.display = hit ? '' : 'none';
        if (hit) shown++;
      }
      this.style.borderColor = (q && !shown) ? '#c22638' : '#ccc';
    });
  }

  /* ── 낱개 갈음 ────────────────────────────────────────────────────────
     줄의 [갈음] 은 공유 폼의 숨은 값을 채우고 파일 선택창을 연다. 제출은 사람이
     아래 [갈아끼우기] 를 눌러서 한다 — `adm/admin.js` 가 그 클릭에 관리자 토큰을
     채우기 때문이다. JS 가 form.submit() 을 부르면 토큰이 빈 채로 가서 반드시 실패한다. */
  var one     = document.getElementById('exdOne');
  var oneFile = document.getElementById('exdOneFile');
  var oneDrop = document.getElementById('exdOneDrop');
  var oneName = document.getElementById('exdOneName');
  var oneTgt  = document.getElementById('exdOneTgt');
  var oneNote = document.getElementById('exdOneNote');
  var oneMode = document.getElementById('exdOneMode');
  var oneTarg = document.getElementById('exdOneTarget');
  var oneRel  = document.getElementById('exdOneRel');
  var oneHref = document.getElementById('exdOneHref');
  var oneTopic= document.getElementById('exdOneTopic');
  var oneWhat = '';

  function oneShow() {
    var fs = oneFile.files;
    if (!fs || !fs.length) { oneName.textContent = '고른 파일 없음'; oneName.className = 'dim'; return; }
    if (fs.length === 1) {
      oneName.textContent = fs[0].name + ' · ' + Math.round(fs[0].size / 1024) + 'KB';
    } else {
      var kb = 0, nm = [];
      for (var i = 0; i < fs.length; i++) { kb += fs[i].size; nm.push(fs[i].name); }
      oneName.textContent = fs.length + '개 · ' + Math.round(kb / 1024) + 'KB — '
        + nm.slice(0, 4).join(', ') + (nm.length > 4 ? ' 외 ' + (nm.length - 4) + '개' : '');
    }
    oneName.className = '';
  }
  if (one && oneFile && oneDrop) {
    oneDrop.addEventListener('click', function () { oneFile.click(); });
    oneFile.addEventListener('change', oneShow);
    oneDrop.addEventListener('dragover', function (e) {
      e.preventDefault(); oneDrop.className = 'drop over';
    });
    oneDrop.addEventListener('dragleave', function () { oneDrop.className = 'drop'; });
    oneDrop.addEventListener('drop', function (e) {
      e.preventDefault(); oneDrop.className = 'drop';
      if (!e.dataTransfer || !e.dataTransfer.files || !e.dataTransfer.files.length) return;
      try { oneFile.files = e.dataTransfer.files; } catch (err) {
        alert('이 브라우저는 끌어다 놓기를 지원하지 않습니다. 눌러서 고르십시오.');
        return;
      }
      oneShow();
    });
    document.getElementById('exdOneCancel').addEventListener('click', function () {
      one.className = 'box';
      oneFile.value = ''; oneShow();
    });

    var reps = document.querySelectorAll('.exdep button.rep[data-mode]');
    for (var r = 0; r < reps.length; r++) {
      reps[r].addEventListener('click', function () {
        var mode = this.getAttribute('data-mode');
        oneMode.value = mode;
        /* 「넣기」만 여러 개를 고를 수 있다. 갈음은 자리가 하나다. */
        oneFile.multiple = (mode === 'add');
        oneTopic.value = this.getAttribute('data-topic') || '';

        if (mode === 'add') {
          oneRel.value = ''; oneHref.value = '';
          oneTarg.value = this.getAttribute('data-target');
          oneWhat = this.getAttribute('data-label');
          oneTgt.textContent = oneWhat;
          oneNote.innerHTML = '여러 개를 한 번에 고르셔도 됩니다 — <b>파일 이름을 보고</b> '
            + '각자 갈 자리로 갑니다. 서버에 이미 있는 것은 갈아끼우고, 내용이 같으면 '
            + '건드리지 않습니다. 폴더가 끼는 것(<code>figs/</code> 479개 · '
            + '<code>assets/</code>)은 ZIP 이 빠릅니다.';
          oneFile.removeAttribute('accept');
        } else if (mode === 'subject') {
          oneHref.value = this.getAttribute('data-href');
          oneRel.value  = '';
          oneTarg.value = 'pd';
          oneWhat = this.getAttribute('data-label');
          oneTgt.textContent = oneWhat;
          oneNote.innerHTML = '빌드가 만든 <code>' +
            oneHref.value.replace(/\.html$/, '.js') + '</code> 를 올리십시오. ' +
            '<b>이 과목 한 줄만</b> 갈아끼웁니다 — 나머지 과목은 서버 것이 그대로 남습니다.';
          oneFile.setAttribute('accept', '.js');
        } else {
          oneRel.value  = this.getAttribute('data-rel');
          oneHref.value = '';
          oneTarg.value = this.getAttribute('data-target');
          oneWhat = oneRel.value;
          oneTgt.textContent = (oneTarg.value === 'shell' ? '/exam/' : '/exam/pd/'
            + document.getElementById('exdPd').value + '/') + oneWhat;
          oneNote.innerHTML = (oneTarg.value === 'shell'
            ? '<b>공용 껍데기</b>입니다 — 모든 문제집 화면이 함께 바뀝니다. '
            : '') + '같은 이름의 파일로만 갈 수 있습니다. 내용이 이미 같으면 쓰지 않습니다.';
          var ext = oneWhat.indexOf('.') >= 0 ? oneWhat.substring(oneWhat.lastIndexOf('.')) : '';
          if (ext) oneFile.setAttribute('accept', ext);
        }
        one.className = 'box on';
        oneFile.value = ''; oneShow();
        if (one.scrollIntoView) one.scrollIntoView({ behavior: 'smooth', block: 'center' });
        oneFile.click();
      });
    }
  }

  window.exdOneGo = function () {
    var fs = oneFile.files;
    if (!fs || !fs.length) { alert('파일을 먼저 고르십시오.'); return false; }
    var add = (oneMode.value === 'add');
    if (!add && !oneRel.value && !oneHref.value) {
      alert('무엇을 갈아끼울지 먼저 고르십시오.'); return false;
    }
    var extra = (oneTarg.value === 'shell')
      ? '\n\n공용 껍데기는 모든 문제집이 함께 쓰는 화면입니다.' : '';
    var what = add ? (fs.length + '개 파일을 ' + oneWhat + ' 에 넣습니다.')
                   : (oneWhat + ' 을 「' + fs[0].name + '」 으로 갈아끼웁니다.');
    return confirm(what + '\n이미 있는 것은 갈아끼웁니다 — 되돌리려면 예전 파일을 '
                 + '다시 올려야 합니다.' + extra + '\n\n계속할까요?');
  };

  window.exdApply = function () {
    var f = file.files && file.files[0];
    if (!f) { alert('ZIP 파일을 먼저 고르십시오.'); return false; }
    var extra = (tsel && tsel.value === 'shell')
      ? '\n\n공용 껍데기는 모든 문제집이 함께 쓰는 화면입니다.' : '';
    if (!confirm('서버 파일을 갈아끼웁니다. 되돌리려면 예전 파일을 다시 올려야 합니다.'
                 + extra + '\n\n계속할까요?')) return false;
    document.getElementById('exdAct').value = 'apply';
    return true;
  };
})();
</script>

<?php
require_once './admin.tail.php';
