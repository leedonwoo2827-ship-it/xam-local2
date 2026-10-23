<?php
if (!defined('_GNUBOARD_')) exit;

/**
 * 관리자 메뉴 등록 — 파일 추가만으로 끝난다. 코어 수정 0.
 *
 * 근거: adm/admin.lib.php L751~774 가 `/^admin.menu([0-9]{3}).*\.php$/` 로
 *       adm/ 를 스캔해 include 한다. 배포본은 100/200/300/400/500/900 만 쓰므로
 *       600 대역은 비어 있고, 이 파일명은 배포본에 없어서 코어 업데이트에도 살아남는다.
 *
 * 배열 형식: array(코드, 라벨, URL, 앵커ID[, 숨김])
 *   · 첫 항목 x00000 이 그룹 헤더
 *   · 5번째 요소 1 = 메뉴에서 숨김
 *
 * 권한: 최고관리자는 auth_check() 에서 무조건 통과한다.
 *       부관리자에게 주려면 여기 등록된 코드를 `관리권한` 화면에서 부여한다
 *       (등록해두면 권한 부여 드롭다운에 자동으로 뜬다).
 */

$menu['menu600'] = array(
    array('600000', '문제은행',      G5_ADMIN_URL.'/exam_import.php',       'exam'),
    array('600200', '질문 검수',     G5_ADMIN_URL.'/exam_qna_list.php',     'exam_qna'),
    array('600250', '답변 초안 설정', G5_ADMIN_URL.'/exam_llm.php',          'exam_llm'),
    array('600300', '과목게시판',    G5_ADMIN_URL.'/exam_board_sync.php',   'exam_board'),
    array('600400', '문제 임포트',   G5_ADMIN_URL.'/exam_import.php',       'exam_import'),
    array('600450', '문제 목록',     G5_ADMIN_URL.'/exam_problem_list.php', 'exam_problem'),
    array('600500', '포인트 지급',   G5_ADMIN_URL.'/exam_credit_grant.php', 'exam_credit'),
    array('600600', '수강 신청',     G5_ADMIN_URL.'/exam_orders.php',       'exam_orders'),

    /* exam_qna_form.php 는 등록하지 않는다 — 목록에서만 들어가는 상세 화면이고,
     * 메뉴에 올리면 qa_id 없이 열려 "질문을 찾을 수 없습니다"만 보인다.
     * $sub_menu = '600200' 을 공유하므로 권한은 '질문 검수'와 같이 움직인다. */

    /* 문항 DB 뷰어·편집 (2026-08-04). 카페24에 phpMyAdmin 이 없어서 "서버에 실제로
     * 무엇이 들어 있나" 를 볼 곳이 없었다. 정답 오류 신고가 오면 여기서 즉시 고친다.
     * ★ 고치면 edited_by 가 남아 재임포트가 그 행을 건너뛴다 — 로컬과 갈리므로
     *   화면이 보여주는 '로컬 반영용 JSON' 을 #/questions 에 반영할 것. */
    array('600460', '문항 DB 뷰어',  G5_ADMIN_URL.'/exam_problem_form.php', 'exam_problem_form'),

    /* 품목 관리 (2026-08-21 메뉴 등록). 파일은 전부터 있었지만 메뉴에 없어서
     * "FTP 로 올려 쓰고 지우는 1회용" 이었다. 품목을 추가할 때마다 필요하므로
     * 상시 화면으로 올린다 — 품목 추가 = ex_product 1행 + 임포트가 원칙이고,
     * 그 1행을 넣는 유일한 자리가 여기다(카페24에 phpMyAdmin 이 없다).
     * ★ 파일 안에 `$is_admin != 'super'` 하드 게이트가 그대로 있다. 부관리자에게
     *   권한을 줘도 막힌다 — 품목 삭제가 회원 응시기록을 참조하는 문항을 건드리기
     *   때문이다. 그 게이트를 풀 것인지는 따로 결정한다. */
    array('600700', '품목 관리',     G5_ADMIN_URL.'/seed_pd.php',           'exam_pd'),

    /* 정적 파일 반입 (2026-08-21). FileZilla 를 시험운용자마다 줄 수 없어서 만들었다.
     * 문항은 이미 exam_import.php 로 FTP 를 벗어났는데 정적 산출물
     * (problems.js·videos.js·theory*.js·figs/)은 아직 FTP 뿐이었다.
     * ★ 이 코드를 `관리권한` 화면에서 부관리자에게 주면 그 사람은 FTP 없이
     *   콘텐츠를 올릴 수 있다. `.php` 는 이 화면이 받지 않는다. */
    array('600800', '파일 반입',     G5_ADMIN_URL.'/exam_deploy.php',       'exam_deploy'),

    // ↓ 아직 만들지 않았다. 해당 단계에서 주석을 푼다.
    // array('600100', '대시보드',      G5_ADMIN_URL.'/exam_index.php',        'exam_index'),
);
