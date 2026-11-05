<?php
/**
 * /exam/check.php — 문제풀이 화면.  탭 한 세트: 홈 · 이론 · 문제집 · 과목게시판
 *
 * ── 왜 정적 HTML 에서 PHP 로 옮겼는가 ──────────────────────────────────────
 * 과목게시판이 그누보드 게시판(PHP)이고, 정적 HTML 안에 자연스럽게 들어가지 않는다.
 * mypage.php · buy.php 가 이미 그누보드 테마 안에서 돌고 헤더 통일도 그 방식이라
 * 같은 자리로 옮기는 것이 일관된다.
 *
 * 부수적으로 얻은 것:
 *   · 헤더·푸터·브랜드가 테마 한 곳에서 온다. 템플릿의 nav 사본이 사라졌다
 *   · EXAM_CFG 를 **DB 를 보고** 주입한다. build_check.py 는 DB 를 못 봤다
 *   · pd 를 ex_product 로 검증한다. 없는 품목·오타가 화면까지 오지 않는다
 *
 * ⚠ 잃은 것: file:// 로컬 미리보기. 게시판 탭이 서버 없이 성립하지 않으므로 감수했다.
 *   문제 데이터 검수는 build_check.py 의 빌드 리포트로 한다.
 *
 * ── 파일 구성 ──────────────────────────────────────────────────────────────
 *   이 파일          화면 골격 + EXAM_CFG 주입 (저장소 소스)
 *   assets/check.css 스타일          ┐ 예전 check_template.html 의
 *   assets/check.js  렌더·채점 로직  ┘ <style> · <script> 를 파일로 뺀 것
 *   pd/<pd_id>/*.js  이론·영상·정적 문제 (빌드 산출물. 문제집별로 분리돼 있다)
 */
include_once('../common.php');

/* ── 문제집 확정 ────────────────────────────────────────────────────────────
 * 형식 검증만으로는 부족하다 — 'sqldd' 도 정규식을 통과해 살아 있는 품목처럼 행동한다.
 * ex_product 에 실재하고 **문제가 실제로 있는지**까지 본다.
 * 문제 0건인 품목으로 들어오면 탭을 눌러도 빈 화면이라 목록으로 돌려보낸다.
 */
$pd_want = preg_match('/^[a-z0-9\-]{1,20}$/', isset($_GET['pd']) ? $_GET['pd'] : '')
         ? $_GET['pd'] : '';

$prod = null;
if ($pd_want !== '') {
    $prod = sql_fetch("select pd_id, pd_name from ex_product
                        where pd_id = '" . sql_real_escape_string($pd_want) . "' and pd_open = 1");
}
if (!$prod) {
    // 노출 중이고 문제가 있는 첫 품목
    $prod = sql_fetch("select d.pd_id, d.pd_name from ex_product d
                        where d.pd_open = 1
                          and exists (select 1 from ex_problem x
                                       where x.pd_id = d.pd_id and x.pr_open = 1)
                        order by d.pd_sort, d.pd_id limit 1");
}
if (!$prod) {
    // 문제가 하나도 임포트되지 않은 상태. 빈 화면 대신 문제집 목록으로.
    goto_url(G5_URL . '/exam/');
}

$pd      = $prod['pd_id'];
$pd_name = $prod['pd_name'];

/* ── 과목 · 회차 ────────────────────────────────────────────────────────────
 * 과목게시판 칩과 breadcrumb 이 쓴다. check.js 가 api/problems.php 로 다시 받지만,
 * **첫 화면이 네트워크를 기다리지 않게** 여기서도 넣어준다(첫 페인트 품질).
 */
$subjects = array();
$res = sql_query("select distinct sj_no, sj_name from ex_problem
                   where pd_id = '" . sql_real_escape_string($pd) . "'
                     and pr_open = 1 and sj_name <> ''
                   order by sj_no", false);
while ($res && $r = sql_fetch_array($res)) {
    $subjects[] = array('sj_no' => (int)$r['sj_no'], 'sj_name' => $r['sj_name']);
}

$cnt = sql_fetch("select count(*) as n, count(distinct rd_no) as rd from ex_problem
                   where pd_id = '" . sql_real_escape_string($pd) . "' and pr_open = 1");

/* ── 브랜드 ─────────────────────────────────────────────────────────────────
 * head.php 도 같은 것을 읽지만, 여기서 EXAM_CFG 에 넣어야 check.js 의 breadcrumb 이
 * 브랜드를 안다. include_once 라 두 번 읽히지 않는다.
 */
@include_once(G5_PATH . '/exam/brand.php');
if (!isset($EX_BRAND))      $EX_BRAND      = 'XAMpass';
if (!isset($EX_BRAND_HTML)) $EX_BRAND_HTML = '<i>XAM</i>pass';

/* ── check.js 에 넘길 설정 ──────────────────────────────────────────────────
 * api 를 './api/' 로 고정한다 — 이 파일이 /exam/ 에 있으므로 상대경로가 맞다.
 * data 는 문제집별 정적 데이터 기준 경로다(pd/<pd_id>/).
 */
$EXAM_CFG = array(
    'api'   => './api/',
    'pd'    => $pd,
    'data'  => 'pd/' . $pd . '/',
    'brand' => array('brand' => $EX_BRAND, 'brand_html' => $EX_BRAND_HTML),
    'product' => array(
        'pd_id'    => $pd,
        'pd_name'  => $pd_name,
        'problems' => (int)$cnt['n'],
        'rounds'   => (int)$cnt['rd'],
        'subjects' => $subjects,
    ),
);

$g5['title'] = $pd_name . ' 문제집';

/* 테마 카드(#container 의 흰 배경·테두리·패딩)를 벗는다 — theme/axexam/head.php 참조.
   이 화면은 .page(배경) 와 .wrap(폭) 을 스스로 갖고 있어서 카드가 한 겹 더 필요 없다.
   ⚠ head.php 를 include 하기 전에 켜야 한다. head.php 가 #container 를 그리는 시점에
     이미 값이 있어야 클래스가 붙는다. */
$ex_bare = true;

include_once(G5_PATH . '/head.php');

$ex_data = 'pd/' . rawurlencode($pd) . '/';
$ex_v    = function ($f) { $p = G5_PATH . '/exam/' . $f; return @filemtime($p) ?: 0; };
?>

<link rel="stylesheet" href="<?php echo G5_URL ?>/exam/assets/style.css?v=<?php echo $ex_v('assets/style.css') ?>">
<link rel="stylesheet" href="<?php echo G5_URL ?>/exam/assets/check.css?v=<?php echo $ex_v('assets/check.css') ?>">

<script>window.EXAM_CFG = <?php echo json_encode($EXAM_CFG, JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES) ?>;
/* 구 이름 별칭 — check.js 안에서 아직 참조한다. 한 릴리스만 유지한다. */
window.EXAM_API = EXAM_CFG.api; window.EXAM_PD = EXAM_CFG.pd;</script>

<div class="page">
  <?php /* breadcrumb — 기획서의 `XAMPASS > SQLD 문제집 > 이론 / 문제풀이`.
           내용은 check.js 의 updateCrumb() 가 채운다(탭을 바꾸면 같이 바뀌어야 한다).
           서버에서 첫 단계까지 그려두면 JS 로딩 전 깜빡임이 줄어든다. */ ?>
  <div class="crumb-bar"><div class="wrap">
    <div class="crumb" id="crumb">
      <svg class="ic"><use href="#i-list"></use></svg>
      <a href="<?php echo G5_URL ?>/exam/"><?php echo htmlspecialchars($EX_BRAND) ?></a>
      <span class="sep">›</span><b><?php echo htmlspecialchars($pd_name) ?> 문제집</b>
    </div>
  </div></div>

  <div class="wrap">
    <div class="head-block">
      <h1 id="pgTitle"><?php echo htmlspecialchars($pd_name) ?></h1>
      <div class="sub" id="pgSub">이론 요약과 회차별 모의고사 — 해설 영상 · 정답 체크</div>
    </div>

    <?php /* 탭 한 세트. 전역 네비(문제집·문제풀기·이론·수강신청)와 층위를 분리해
             제목 아래에 둔다. 같은 줄에 두면 어디가 어디인지 안 잡힌다.
             quiz 는 내부 이름이고 라벨은 '문제집' 이다. */ ?>
    <div class="modes" id="modes">
      <button data-m="home">홈</button>
      <button data-m="theory">이론</button>
      <button data-m="quiz">문제집</button>
      <button data-m="board">과목게시판</button>
    </div>

    <div class="subtabs" id="subtabs"></div>

    <div class="layout" id="layout">
      <div>
        <div class="filters" id="filters" style="display:none">
          <select class="input" id="fSubject" style="max-width:220px"><option value="">전체 과목</option></select>
        </div>
        <div id="list"></div>
      </div>
      <aside class="side" id="side">
        <div class="side-card">
          <h3><span class="icon-box sm soft"><svg class="ic ic-sm"><use href="#i-check-circle"></use></svg></span> 채점 현황</h3>
          <div class="gauge-wrap"><div id="gauge"></div>
            <div><div class="big"><span id="scoreNum">0</span> <small>/ <span id="scoreTot">0</span></small></div><div class="k2" id="scoreK">입력한 문항</div></div></div>
          <div class="side-actions">
            <button class="btn btn-blue btn-block" onclick="grade()"><svg class="ic"><use href="#i-check"></use></svg> 제출 · 기록</button>
            <button class="btn btn-outline btn-block" onclick="reveal()">정답 보기</button>
            <button class="btn btn-outline btn-block" onclick="resetAll()"><svg class="ic"><use href="#i-refresh"></use></svg> 초기화</button>
          </div>
          <?php /* 채점 후 check.js 가 채운다. 성적표는 로그인 회원만 가능하다 —
                   grade.php 가 mb_id 있을 때만 기록하므로 비회원은 at_id 가 없다. */ ?>
          <div class="side-actions" id="rpLink" style="display:none"></div>
        </div>
        <div class="side-card">
          <h3><span class="icon-box sm soft"><svg class="ic ic-sm"><use href="#i-play"></use></svg></span> 해설 영상</h3>
          <div class="vid-list" id="vidList"><div class="vid-empty">이 회차의 영상이 없습니다.</div></div>
        </div>
      </aside>
    </div>
  </div>
</div>

<?php /* 영상은 유튜브 embed 다. <video src> 를 쓰지 않는다 — mp4 411MB 를 호스팅에서 뺐다.
         닫을 때 innerHTML="" 로 비워야 재생이 멈춘다(iframe 은 pause() 가 없다). */ ?>
<div class="vmodal" id="vmodal"><span class="vclose" onclick="closeVid()">×</span><div class="box" id="vbox"></div></div>
<div class="toast" id="toast"></div>

<?php
/* 정적 데이터 — 문제집별로 pd/<pd_id>/ 에 있다.
 *
 * 왜 문제집별로 나누는가: 예전에는 06/ 이 /www/exam/ 에 납작하게 복사돼서
 * 두 번째 문제집의 problems.js · theory_content.js · figs/ 가 첫 번째 것을 덮어썼다.
 *
 * problems.js 는 싣지 않는다 — 서버에서는 api/problems.php 가 이기고,
 * 정답이 박힌 400KB 를 매번 내려보낼 이유가 없다. 이론·영상은 API 가 없어 필요하다.
 * (theory_content.js 는 DB 가 아니라 여기 구워져 있다 — UPLOAD-NOW.md §4 참조)
 *
 * @filemtime 으로 캐시를 무효화한다. 파일이 없으면 0 이고, 그때는 check.js 가
 * THEORY=[] 로 떨어져 "이론 자료가 없습니다" 를 보여준다(죽지 않는다).
 */
foreach (array('theory.js', 'theory_content.js', 'videos.js') as $ex_f) {
    $ex_rel = 'pd/' . $pd . '/' . $ex_f;
    if (!is_readable(G5_PATH . '/exam/' . $ex_rel)) continue;
    echo '<script src="' . G5_URL . '/exam/' . $ex_data . $ex_f
       . '?v=' . $ex_v($ex_rel) . '"></script>' . PHP_EOL;
}
?>
<script src="<?php echo G5_URL ?>/exam/assets/ui.js?v=<?php echo $ex_v('assets/ui.js') ?>"></script>
<script src="<?php echo G5_URL ?>/exam/assets/check.js?v=<?php echo $ex_v('assets/check.js') ?>"></script>

<?php
include_once(G5_PATH . '/tail.php');
