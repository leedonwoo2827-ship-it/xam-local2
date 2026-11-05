/* check.js — 문제풀이 화면 로직.  check.php 가 싣는다.
 *
 * 예전에는 check_template.html 안의 인라인 <script> 였다. PHP 로 전환하면서 파일로 뺐다.
 * 렌더·채점·필터·답안복원 로직은 그대로다 — 옮기면서 고친 것만 아래에 적는다.
 *
 * ── 옮기면서 고친 것 ──────────────────────────────────────────────────────
 *  ① PD 를 서버(EXAM_CFG)에서 받는다. 예전에는 `window.EXAM_PD || "sqld"` 였고
 *     **?pd= 를 아예 읽지 않았다** — check.html?pd=bdae-w 가 SQLD 를 보여줬다.
 *     이제 check.php 가 DB 로 검증한 pd 를 주입하므로 폴백이 필요 없다.
 *  ② P 를 const → let 으로 바꾸고 **DS.problems() 를 실제로 쓴다.**
 *     예전에는 ApiDS.problems 가 정의만 되어 있고 호출되지 않아, 서버에서도 항상
 *     구워진 problems.js 를 읽었다. 그래서 관리자에서 문제를 고쳐도 화면에 반영되지 않았다.
 *  ③ ?m= · ?rd= 를 읽는다. 헤더의 '이론' 메뉴가 &m=theory 를 넘기는데 무시되고 있었다.
 *  ④ 탭이 4개다 — 홈 · 이론 · 문제집 · 과목게시판. (예전: 홈 · 이론 · 회차별)
 *  ⑤ breadcrumb 을 서버 문구가 아니라 브랜드·문제집명에서 만든다.
 */
const CIRC="①②③④⑤⑥⑦⑧⑨⑩";
const $=s=>document.querySelector(s);
const CFG=(window.EXAM_CFG||{});
const BRAND=(CFG.brand&&CFG.brand.brand)||"XAMpass";

/* ★ let 이다. 서버 모드에서 DS.problems() 가 갈아끼운다.
   window.PROBLEMS 는 정적 폴백(file:// 로컬 검수) 전용이다. */
let P=(window.PROBLEMS||[]);
let SUBJECTS=[];                       // [{sj_no, sj_name}] — API 가 주면 그것을 쓴다
let ROUNDS=[];                         // [{no, label, count, free}]
let PD_NAME=(CFG.product&&CFG.product.pd_name)||"";

/* ★ let 이다. api/videos.php 가 레벨 제한 영상을 합쳐 넣는다.
   공개 영상만 videos.js 에 구워져 있고, 저자 검토용 링크는 서버가 레벨을 보고 준다 —
   정적 파일에 넣으면 버튼을 숨겨도 링크가 파일 안에 남는다. */
let VIDEOS=(window.VIDEOS||{});
let vidHidden=0;                   // 레벨이 부족해 안 보이는 개수 (라벨·링크는 받지 않는다)
const THEORY=(window.THEORY||[]);
let mode="quiz", curRound=null, curTheory=null, answers={}, graded=false;

/* 문항 페이지 나눔 —
   한 회차가 80문항(빅분기)·50문항(SQLD)이라 전부 그리면 폰에서 4만 px 짜리 문서가 된다.
   실제로 "작은 화면에서 61~70번쯤부터 못 간다"는 보고가 있었다. 브라우저가
   긴 문서를 버티지 못하는 것이라 오류가 안 나고 그냥 안 내려간다 — 사람이 원인을 못 잡는다.
   채점은 그대로 회차 전체로 한다(cur() 는 안 자른다). 자르는 것은 **그리는 것**뿐이다. */
/* ★ 「한 문항씩」 토글이 이 값을 1 로 바꾼다. 대조·검수는 한 문항씩 보는 것이
   편하고, 응시자는 목록이 편하다 — 둘 다 남긴다. */
let PAGE=20;
let page=0;
/* 채점 결과를 들고 있는다. 페이지를 넘기면 카드가 새로 그려지므로,
   보관하지 않으면 2쪽으로 넘어간 순간 정답·해설이 사라진다. */
let lastResults=null;
/* 바로 채점 — 보기 원숫자를 누르면(펜·손가락·마우스 모두 click) 그 문항만 즉시 채점한다.
   {key: result} 로 들고 있다가 쪽을 넘겨 카드가 새로 그려지면 다시 입힌다.
   한 번 채점한 문항은 다시 고를 수 없다(초기화로만 푼다). 「제출·기록」은 회차 전체를
   grade.php 로 보내 성적표·오답노트에 남기는 일만 한다. */
let instant={};

/* ── 풀던 답안 보존 ────────────────────────────────────────────────────
   answers 가 메모리 변수라 새로고침·탭닫기에 날아갔다.
   서버에 저장할 수도 있지만 localStorage 로 충분하다 —
   비로그인도 되고, 왕복이 없고, 스키마 변경도 없다.
   (기기를 옮기면 안 따라온다. 그게 문제가 되면 그때 서버 동기화를 붙인다.) */
const ansKey = r => "exam:ans:" + PD + ":" + (r || "");
function loadAns(){
  try{
    const s = localStorage.getItem(ansKey(curRound));
    const o = s ? JSON.parse(s) : null;
    return (o && typeof o === "object" && !Array.isArray(o)) ? o : {};
  }catch(e){ return {}; }          // 시크릿 모드·차단 환경
}
function saveAns(){
  try{
    if(Object.keys(answers).length) localStorage.setItem(ansKey(curRound), JSON.stringify(answers));
    else                            localStorage.removeItem(ansKey(curRound));
  }catch(e){}                      // 용량 초과 등은 조용히 넘어간다 — 풀이를 막을 이유가 없다
}
let restoreNoticed = false;        // 복원 안내는 최초 1회만 (회차를 오갈 때마다 뜨면 시끄럽다)

/* ── 데이터 소스 추상화 ────────────────────────────────────────────────
   window.EXAM_API 가 있으면(build_check.py --api-base 가 주입) 서버에서 읽고,
   없으면 구워넣은 window.PROBLEMS 로 동작한다.

   이게 있어야 정적 폴백(file:// 더블클릭 = 로컬 문제 검수)이 공짜로 유지된다.
   마크업 1개, JS 1개, 소스만 스왑 — 템플릿을 두 벌로 관리하지 않는다.
   서버에서는 웹(adm/exam_problem_form.php)에서 고친 문제가 화면에 바로 반영되어야
   하므로 problems.js 를 그대로 쓸 수 없다. */
const API = CFG.api || window.EXAM_API || "";

/* ★ PD 는 서버가 정한다.
   check.php 가 ?pd= 를 ex_product 로 검증해 EXAM_CFG.pd 로 내려준다 —
   형식만 맞는 오타('sqldd')나 없는 품목이 여기까지 오지 않는다.
   'sqld' 폴백을 두지 않는 이유: 문제집이 여러 개인 지금은 폴백이
   "다른 문제집을 열었는데 SQLD 가 뜨는" 경로가 된다. */
const PD  = CFG.pd || window.EXAM_PD || "";

const StaticDS = {
  async problems(){
    return {problems:P,
            product:{pd_id:PD, pd_name:PD_NAME},
            rounds:uniq(P.map(p=>p.round)).map(r=>({no:parseInt(r)||0, label:r})),
            subjects:uniq(P.map(p=>p.subject)).map((s,i)=>({sj_no:i+1, sj_name:s}))};
  },
  /* 클라이언트 채점 — 정답이 problems.js 안에 있으니 그대로 판정한다. */
  async grade(round, ans){
    const rows=cur(), results=[]; let ok=0;
    rows.forEach(p=>{ const k=keyOf(p), chosen=(k in ans)?ans[k]:-1;
      const good = chosen===p.answer_index; if(good) ok++;
      results.push({key:k, ok:good, chosen:chosen,
                    answer_index:p.answer_index, explanation:p.explanation}); });
    const tot=rows.length;
    return {score:{correct:ok, total:tot, pct:tot?Math.round(ok/tot*100):0}, results};
  },
  async me(){ return {login:0}; },
};

const ApiDS = {
  async problems(round){
    const r=await fetch(API+"problems.php?pd="+encodeURIComponent(PD)
                          +"&round="+encodeURIComponent(round||""),
                        {credentials:"same-origin"});
    return await r.json();
  },
  /* 서버는 '화면에 보이던 문제 집합'을 알아야 미응답을 셀 수 있다.
     과목·난이도 필터가 걸려 있으면 회차 전체가 아니라 그 부분집합이 채점 대상이다.
     그래서 keys 를 함께 보낸다 — 서버는 이걸 DB 행과 교집합으로만 쓴다. */
  async grade(round, ans, keys){
    const rows=cur();
    const r=await fetch(API+"grade.php", {method:"POST", credentials:"same-origin",
      headers:{"Content-Type":"application/json","X-Exam-Csrf":(window.ME&&ME.csrf)||""},
      body:JSON.stringify({
        pd:PD, round:round, keys:keys||rows.map(keyOf), answers:ans,
        filter:$("#fSubject").value||""
      })});
    return await r.json();
  },
  async me(){
    try{ return await (await fetch(API+"me.php",{credentials:"same-origin"})).json(); }
    catch(e){ return {login:0}; }
  },
};

const DS = API ? ApiDS : StaticDS;

/* 정적 데이터 기준 경로. 문제집별로 pd/<pd_id>/ 아래에 있다.
   예전에는 06/ 이 /www/exam/ 에 납작하게 복사돼 두 번째 문제집이 첫 번째 도식을 덮어썼다.
   CFG.data 가 없으면(옛 빌드) 예전처럼 같은 폴더에서 찾는다 — 하위호환. */
const DATA = CFG.data || "";
const FIGS = DATA + "figs/";

function esc(s){return (s||"").replace(/[&<>]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]));}
function md(s){ s=esc(s);
  s=s.replace(/!\[[^\]]*\]\(([^)\s]+)[^)]*\)/g,(m,u)=>'<img class="fig" src="'+FIGS+u.split(/[\\\/]/).pop()+'" onerror="this.style.display=\'none\'">');
  s=s.replace(/\*\*([^*]+)\*\*/g,'<strong>$1</strong>'); s=s.replace(/`([^`]+)`/g,'<code>$1</code>'); return s; }
// 블록 마크다운 — #2 bundle.py 의 md_blocks 와 같은 규칙(표·불릿·맨텍스트 SQL).
// lesson 의 표/SQL 은 `table`/`sql` 필드가 아니라 지문 안에 텍스트로 들어오는 경우가 많아,
// 이걸 렌더하지 않으면 "| 상품명 | 분류코드 |" 가 그대로 노출된다(영상 덱과도 어긋난다).
const SQL_START=/^\s*(SELECT|INSERT|UPDATE|DELETE|CREATE|ALTER|DROP|WITH|MERGE|TRUNCATE)\b/i;
const SQL_CONT=/^\s*(FROM|WHERE|GROUP\s+BY|ORDER\s+BY|HAVING|UNION|MINUS|INTERSECT|JOIN|LEFT|RIGHT|INNER|FULL|CROSS|OUTER|ON|AND|OR|SET|VALUES|START\s+WITH|CONNECT\s+BY|[(),])/i;
const SQL_OK=/\b(FROM|VALUES|SET)\b|;/i;
const BULLET=/^([-*•·]|\d+[.)])\s+/;   /* · 는 가운뎃점(U+00B7). 지문 145줄이 이걸 쓴다 */
/* ★ 한글 항목 기호 — `ㄱ.` `가.` `①` 로 시작하는 줄은 **한 줄에 하나씩** 낸다.
   BULLET 은 `-`·`1.` 만 알아서, 이런 줄은 그냥 문단에 섞여 한 덩이로 이어붙었다:
     "ㄱ. 주문 테이블 ㄴ. API 호출 로그 ㄷ. CCTV 녹화 영상 ㄹ. XML 파일"
   보기묶음 지문은 항목이 갈려 보이지 않으면 문제를 읽을 수 없다.
   한 글자 + `.`/`)` 로 좁힌다 — "데이터. 이것은" 같은 보통 문장을 잡지 않으려고. */
const ITEM=/^(?:(?:[ㄱ-ㅎ]|[가나다라마바사아자차카타파하])[.)]|[①-⑳㉠-㉭][.)]?|※)\s+/;
function sqlRun(L,i){ if(!SQL_START.test(L[i])) return null;
  const buf=[]; let j=i;
  while(j<L.length && L[j].trim() && (j===i||SQL_START.test(L[j])||SQL_CONT.test(L[j])||/^[ \t]/.test(L[j]))){ buf.push(L[j].replace(/\s+$/,"")); j++; }
  const code=buf.join("\n").trim(); return SQL_OK.test(code)?[j,code]:null; }
function mdTable(rows){
  const cells=rows.map(r=>r.trim().replace(/^\||\|$/g,"").split("|").map(c=>c.trim()));
  let head=[]; if(cells.length>1 && cells[1].every(c=>/^:?-{2,}:?$/.test(c||"-"))){ head=cells[0]; cells.splice(0,2); }
  return "<table class='qtable'>"+(head.length?"<thead><tr>"+head.map(c=>"<th>"+md(c)+"</th>").join("")+"</tr></thead>":"")
    +"<tbody>"+cells.map(r=>"<tr>"+r.map(c=>"<td>"+md(c)+"</td>").join("")+"</tr>").join("")+"</tbody></table>"; }
function mdb(s){
  const L=String(s||"").replace(/\r\n/g,"\n").split("\n"); let out="", i=0;
  while(i<L.length){ const st=L[i].trim();
    if(!st){ i++; continue; }
    if(st.startsWith("```")){ const lang=st.slice(3).trim().toLowerCase(); i++; const buf=[];
      while(i<L.length && !L[i].trim().startsWith("```")){ buf.push(L[i]); i++; } i++;
      const code=buf.join("\n").trim();
      out+="<pre class='sql'><code>"+esc(code)+"</code></pre>"; continue; }
    if(st.startsWith("|")){ const buf=[]; while(i<L.length && L[i].trim().startsWith("|")){ buf.push(L[i]); i++; }
      out+=mdTable(buf); continue; }
    const run=sqlRun(L,i);
    if(run){ i=run[0]; out+="<pre class='sql'><code>"+esc(run[1])+"</code></pre>"; continue; }
    if(BULLET.test(st)){ const buf=[]; while(i<L.length && BULLET.test(L[i].trim())){ buf.push(L[i].trim().replace(BULLET,"")); i++; }
      out+="<ul>"+buf.map(x=>"<li>"+md(x)+"</li>").join("")+"</ul>"; continue; }
    if(ITEM.test(st)){ const buf=[];
      while(i<L.length){ const c=L[i].trim();
        if(!c) break;
        if(ITEM.test(c)) buf.push(c);
        else if(buf.length) buf[buf.length-1]+=" "+c;   /* 접혀 내려온 줄은 앞 항목에 붙인다 */
        else break;
        i++; }
      out+=buf.map(x=>"<p>"+md(x)+"</p>").join(""); continue; }
    const buf=[];
    while(i<L.length){ const c=L[i].trim();
      if(!c||c.startsWith("|")||c.startsWith("```")||BULLET.test(c)||ITEM.test(c)) break;
      if(buf.length&&sqlRun(L,i)) break;
      buf.push(c); i++; }
    out+="<p>"+md(buf.join(" "))+"</p>"; }
  return out; }
/* 지문은 **쓴 대로** 낸다 — 줄바꿈을 보존한다.
 * 표기를 하나씩 알아맞히는 방식은 끝이 없다: `-` 다음에 `·`, `ㄱ.`, `①`, `㉠`, `※`
 * 를 차례로 놓쳤고, **표기가 아예 없는 줄**도 있다(관측치 나열 "8, 16, 24, …").
 * 실측 — 여러 줄 지문 317개 중 186개가 표기가 없거나 섞여 있다.
 * 지문은 사람이 줄을 나눠 쓴 자료라 그 줄이 곧 뜻이다. 문제문·해설은 그대로
 * mdb() 를 쓴다 — 거긴 접힌 줄을 이어붙이는 것이 맞다.
 * 표·SQL·코드는 여기서도 블록으로 묶는다. SQLD 지문이 표와 SQL 덩어리다. */
function mdLines(s){
  const L=String(s||"").replace(/\r\n/g,"\n").split("\n"); let out="", i=0;
  while(i<L.length){ const st=L[i].trim();
    if(!st){ i++; continue; }
    if(st.startsWith("```")){ i++; const buf=[];
      while(i<L.length && !L[i].trim().startsWith("```")){ buf.push(L[i]); i++; } i++;
      out+="<pre class='sql'><code>"+esc(buf.join("\n").trim())+"</code></pre>"; continue; }
    if(st.startsWith("|")){ const buf=[]; while(i<L.length && L[i].trim().startsWith("|")){ buf.push(L[i]); i++; }
      out+=mdTable(buf); continue; }
    const run=sqlRun(L,i);
    if(run){ i=run[0]; out+="<pre class='sql'><code>"+esc(run[1])+"</code></pre>"; continue; }
    out+="<p>"+md(st)+"</p>"; i++; }
  return out; }
function keyOf(p){ return (p.bundle||"")+"#"+(p.number); }
function uniq(a){ return [...new Set(a.filter(v=>v!=null&&v!==""))]; }
/* 회차 라벨. 문제에서 뽑는다 — ROUNDS(ex_round)에는 문제가 0건인 회차도 들어 있어서
   그걸 탭으로 만들면 눌러도 빈 화면이 뜬다. */
function rounds(){ return uniq(P.map(p=>p.round)).sort((a,b)=>(parseInt(a)||0)-(parseInt(b)||0)); }
/* 과목 이름 목록. API 가 주면 그것을(sj_no 순서가 정확하다), 없으면 문제에서 뽑는다. */
function subjectNames(){
  return SUBJECTS.length ? SUBJECTS.map(s=>s.sj_name) : uniq(P.map(p=>p.subject));
}
function cur(){ return P.filter(p=>p.round===curRound
  && (!$("#fSubject").value||(p.subject||"")===$("#fSubject").value)); }
function tableHtml(t){ if(!t||!t.columns) return "";
  let h="<table class='qtable'><thead><tr>"+t.columns.map(c=>"<th>"+esc(String(c))+"</th>").join("")+"</tr></thead><tbody>";
  (t.rows||[]).forEach(r=>{ h+="<tr>"+r.map(c=>"<td>"+esc(String(c))+"</td>").join("")+"</tr>"; }); return h+"</tbody></table>"; }

/* 탭 한 세트 — 홈 · 이론 · 문제집 · 과목게시판.
   quiz 는 내부 이름이고 화면 라벨은 '문제집' 이다(회차별 모의고사가 문제집의 내용이다). */
const MODES=["home","theory","quiz","board"];

function setMode(m){
  if(MODES.indexOf(m)<0) m="home";
  mode=m; graded=false;
  if(m!=="quiz") answers={};       // 이론·홈·게시판에서는 답안 상태를 들고 있을 이유가 없다
  document.querySelectorAll("#modes button").forEach(b=>b.classList.toggle("on",b.dataset.m===m));
  $("#layout").classList.toggle("tmode", m!=="quiz");      // quiz 만 사이드바를 쓴다
  $("#filters").style.display = (m==="quiz") ? "flex" : "none";
  // 홈·게시판에는 하위 탭이 없다(게시판은 과목 칩을 자기 영역 안에 그린다)
  $("#subtabs").style.display = (m==="home"||m==="board") ? "none" : "flex";

  if(m==="quiz"){ const rs=rounds(); curRound=curRound&&rs.includes(curRound)?curRound:(rs[0]||null);
    answers=loadAns();                      // 풀던 답안 복원
    instant={};                             // 복원한 답안은 이미 바로 채점된 것 — 정답이 손에 있으면 다시 칠한다
    P.forEach(p=>{ const k=keyOf(p); if(answers[k]!=null && typeof p.answer_index==="number") instant[k]=judge(p, answers[k]); });
    const n=Object.keys(answers).length;
    if(n && !restoreNoticed){ restoreNoticed=true;
      setTimeout(()=>toast("이전에 선택한 답안 "+n+"개를 불러왔습니다"), 400); }
    $("#pgTitle").textContent="회차별 모의고사 · 정답 체크"; $("#pgSub").textContent="보기 번호를 누르면 바로 정답·해설이 표시됩니다."; }
  else if(m==="theory"){ curTheory=curTheory||(THEORY[0]&&THEORY[0].href)||null;
    $("#pgTitle").textContent="이론 요약노트"; $("#pgSub").textContent="과목별 핵심 개념 요약입니다."; }
  else if(m==="board"){
    $("#pgTitle").textContent="과목게시판"; $("#pgSub").textContent="과목별 질문과 답변입니다. 문제를 풀다 막히면 여기에 물어보세요."; }
  else{ /* home — 제목은 문제집 이름이다. 하드코딩하지 않는다. */
    $("#pgTitle").textContent=(PD_NAME||"문제집");
    $("#pgSub").textContent="이론 요약과 회차별 모의고사 — 해설 영상 · 정답 체크"; }

  // 주소를 상태와 맞춘다. 새로고침·공유·뒤로가기가 같은 화면으로 돌아와야 한다.
  syncUrl();
  buildSub(); render();
}

/* ?m= · ?rd= 를 주소에 반영한다. history.replaceState 라 방문 기록을 더럽히지 않는다
   (탭을 여러 번 누른 뒤 뒤로가기를 눌렀을 때 사이트를 못 벗어나는 것을 막는다). */
function syncUrl(){
  try{
    const u=new URL(location.href);
    if(PD) u.searchParams.set("pd",PD);
    if(mode==="home") u.searchParams.delete("m"); else u.searchParams.set("m",mode);
    if(mode==="quiz"&&curRound) u.searchParams.set("rd",curRound); else u.searchParams.delete("rd");
    history.replaceState(null,"",u.pathname+"?"+u.searchParams.toString());
  }catch(e){ /* file:// 에서는 URL API 가 제한될 수 있다. 무시한다. */ }
}
function goTheory(href){ curTheory=href; setMode("theory"); }
function goQuiz(r){ curRound=r; setMode("quiz"); }
function buildSub(){
  const box=$("#subtabs");
  if(mode==="home"){ box.innerHTML=""; return; }
  if(mode==="quiz"){ box.innerHTML=rounds().map(r=>'<button data-v="'+r+'"'+(r===curRound?' class="on"':'')+'>'+r+'</button>').join("");
    box.querySelectorAll("button").forEach(b=>b.onclick=()=>{ curRound=b.dataset.v; answers=loadAns(); graded=false; lastResults=null; page=0; buildSub(); renderVideos(); render(); updateCrumb(); }); }
  else{ box.innerHTML=THEORY.map(t=>'<button data-v="'+t.href+'"'+(t.href===curTheory?' class="on"':'')+'>'+esc(t.label)+'</button>').join("");
    box.querySelectorAll("button").forEach(b=>b.onclick=()=>{ curTheory=b.dataset.v; buildSub(); render(); updateCrumb(); }); }
}
/* breadcrumb — 기획서의 `XAMPASS > SQLD 문제집 > 이론 / 문제풀이`.
   브랜드도 문제집명도 하드코딩하지 않는다: 브랜드는 EXAM_CFG.brand, 이름은 API/DB 다. */
function updateCrumb(){
  const box=$("#crumb");
  if(!box) return;
  const items=[{t:BRAND, href:"/exam/"}];
  if(PD_NAME) items.push({t:PD_NAME+" 문제집", href:"detail.php?pd="+encodeURIComponent(PD)});

  /* 홈에서는 여기서 끝낸다 — 문제집명 자체가 홈이라 '… › 홈' 은 겹친다. */
  if(mode==="quiz"){
    items.push({t:"회차별 모의고사"});
    if(curRound) items.push({t:curRound});
  }else if(mode==="theory"){
    items.push({t:"이론"});
    const t=THEORY.find(x=>x.href===curTheory);
    if(t) items.push({t:t.label});
  }else if(mode==="board"){
    items.push({t:"과목게시판"});
    if(boardSj>0){ const s=SUBJECTS.find(x=>x.sj_no===boardSj); if(s) items.push({t:s.sj_name}); }
  }

  box.innerHTML='<svg class="ic"><use href="#i-list"></use></svg>'
    + items.map((it,i)=>{
        const t=esc(it.t);
        const node = it.href ? '<a href="'+esc(it.href)+'">'+t+'</a>' : '<b>'+t+'</b>';
        return (i?'<span class="sep">›</span>':'')+node;
      }).join("");
}

function render(){
  updateCrumb();
  const list=$("#list");
  if(mode==="home"){ renderHome(list); return; }
  if(mode==="board"){ renderBoard(list); return; }
  if(mode==="theory"){
    if(!THEORY.length){ list.innerHTML='<div class="empty">이론 자료가 없습니다.</div>'; return; }
    list.innerHTML=theoryVidBar()+'<div id="tbody" class="theorybox"></div>';
    loadTheory(curTheory||THEORY[0].href); return;
  }
  const rows=cur();
  if(!rows.length){ list.innerHTML='<div class="empty">표시할 문제가 없습니다.</div>'; updateGauge(); return; }

  /* 회차 전체(rows)는 그대로 두고 이 쪽에 보일 것만 잘라낸다.
     회차·필터를 바꾸면 goPage(0) 로 되돌아가지만, 범위가 줄어 쪽수가 모자랄 수도 있어
     여기서 한 번 더 가둔다(예: 3쪽을 보다가 과목 필터를 걸어 1쪽밖에 안 남는 경우). */
  const pages=Math.max(1, Math.ceil(rows.length/PAGE));
  if(page>=pages) page=pages-1;
  if(page<0) page=0;
  const view=rows.slice(page*PAGE, (page+1)*PAGE);

  list.innerHTML=pagerHtml(page,pages,rows.length)+view.map(p=>{
    const k=keyOf(p);
    let opts=(p.choices||[]).map((c,ci)=>'<div class="opt" data-k="'+k+'" data-ci="'+ci+'"><span class="cn">'+(CIRC[ci]||(ci+1))+'</span><span>'+md(c)+'</span></div>').join("");
    let mid="";
    if(p.passage) mid+='<div class="passage">'+mdLines(p.passage)+'</div>';
    if(p.sql) mid+='<pre class="sql"><code>'+esc(p.sql)+'</code></pre>';
    if(p.table) mid+=tableHtml(p.table);
    (p.figures||[]).forEach(f=>{ mid+='<img class="fig" src="'+FIGS+f+'" onerror="this.style.display=\'none\'">'; });
    return '<div class="qcard" data-k="'+k+'"><div class="qhead"><span class="qnum">'+esc(p.round)+' · '+(p.number!=null?p.number+'번':'')+'</span>'
      +(p.subject?'<span class="pill pill-teal"><span class="dot"></span>'+esc(p.subject)+'</span>':'')
      +(p.difficulty?'<span class="pill pill-orange">난이도 '+esc(p.difficulty)+'</span>':'')+'</div>'
      +'<div class="q">'+mdb(p.question)+'</div>'+mid+'<div class="opts">'+opts+'</div>'
      /* 해설은 빈 껍데기로 둔다 — 채점 응답(DS.grade)이 채운다.
         서버 채점(ApiDS)일 때 정답·해설이 렌더 시점에 DOM 에 없어야 하기 때문이다. */
      +'<div class="expl"></div></div>';
  }).join("")+pagerHtml(page,pages,rows.length);
  document.querySelectorAll(".opt").forEach(el=>{ if(answers[el.dataset.k]===+el.dataset.ci) el.classList.add("sel"); });
  /* 채점한 뒤 쪽을 넘기면 카드가 새로 그려진다 — 보관해 둔 결과를 다시 입힌다.
     applyResults 는 DOM 에 없는 문항을 건너뛰므로 이 쪽 것만 칠해진다. */
  applyResults(Object.values(instant));
  if(graded && lastResults) applyResults(lastResults);
  updateGauge();
}

/* 쪽 넘김 막대. 위·아래 두 곳에 같은 것을 둔다 —
   80문항을 다 내려간 사람이 다시 위로 올라가 눌러야 하면 그건 안 넘기는 것과 같다. */
function pagerHtml(pg, pages, total){
  /* 「한 문항씩」 토글은 쪽이 하나뿐이어도 낸다 — 그 상태를 되돌릴 방법이
     화면에 없으면 갇힌다. 쪽 번호만 pages<2 일 때 접는다. */
  const size='<div class="pg-size">'
    +'<button class="pg-sz'+(PAGE===20?' on':'')+'" onclick="setPageSize(20)">20문항씩</button>'
    +'<button class="pg-sz'+(PAGE===1?' on':'')+'" onclick="setPageSize(1)">한 문항씩</button></div>';
  if(pages<2) return '<div class="pager">'+size+'</div>';
  const from=pg*PAGE+1, to=Math.min(total,(pg+1)*PAGE);
  let h='<div class="pager">'+size
       +'<button class="pg-nav"'+(pg?'':' disabled')+' onclick="goPage('+(pg-1)+')">‹ 이전</button>';
  /* 한 문항씩일 때는 번호 버튼이 80개가 된다 — 그건 넘김 막대가 아니라 벽이다.
     대신 「47 / 80」 만 보여준다. */
  if(PAGE===1){
    h+='<span class="pg-cur">'+(pg+1)+' / '+pages+'</span>';
  }else{
    h+='<div class="pg-nums">';
    for(let i=0;i<pages;i++) h+='<button class="pg-n'+(i===pg?' on':'')+'" onclick="goPage('+i+')">'+(i+1)+'</button>';
    h+='</div>';
  }
  h+='<button class="pg-nav"'+(pg<pages-1?'':' disabled')+' onclick="goPage('+(pg+1)+')">다음 ›</button>'
    +'<span class="pg-info">'+from+'–'+to+' / '+total+'문항</span></div>';
  return h;
}
/* 쪽 크기를 바꿔도 **보고 있던 문항에 머문다.** 20→1 로 바꿨는데 1번으로
   튕기면 47번을 다시 찾아가야 한다. 첫 번째로 보이던 문항의 자리를 기준으로 옮긴다. */
function setPageSize(n){
  if(PAGE===n) return;
  const firstIdx=page*PAGE;
  PAGE=n;
  page=Math.floor(firstIdx/PAGE);
  goPage(page);
}
function goPage(n){
  page=n; render();
  /* 쪽을 넘겼는데 화면이 그대로면 넘어간 줄 모른다. 목록 머리로 올린다.
     scrollIntoView 대신 좌표를 쓰는 이유: 상단 네비가 고정이라 제목이 그 밑에 깔린다. */
  const el=$("#list");
  if(el){ const y=el.getBoundingClientRect().top+window.pageYOffset-70;
          window.scrollTo({top:Math.max(0,y), behavior:"smooth"}); }
}

function judge(p, ci){
  return {key:keyOf(p), ok:ci===p.answer_index, chosen:ci, answer_index:p.answer_index, explanation:p.explanation};
}
document.addEventListener("click",async e=>{
  const o=e.target.closest(".opt"); if(!o||graded||mode!=="quiz") return;
  const k=o.dataset.k, ci=+o.dataset.ci;
  if(instant[k]) return;                     // 이미 채점한 문항
  answers[k]=ci; saveAns();
  o.parentElement.querySelectorAll(".opt").forEach(x=>x.classList.remove("sel")); o.classList.add("sel","tap");
  const p=P.find(q=>keyOf(q)===k); if(!p) return;
  let r=null;
  if(typeof p.answer_index==="number") r=judge(p, ci);
  else{                                      // 정답이 내려오지 않은 서버 모드 — 그 문항만 물어본다
    try{ const res=await DS.grade(curRound, {[k]:ci}, [k]); r=res&&res.results&&res.results.find(x=>x.key===k); }catch(_){}
    if(!r){ toast("채점에 실패했습니다. 잠시 후 다시 시도해 주세요."); return; }
  }
  instant[k]=r; applyResults([r]);
  const card=o.closest(".qcard"); if(card) card.classList.add("done", r.ok?"is-ok":"is-ng");
  updateGauge();
});
function updateGauge(){
  if(mode!=="quiz") return;
  const rows=cur(), tot=rows.length;
  if(!graded){ const ans=rows.filter(p=>answers[keyOf(p)]!=null).length;
    const ok=rows.filter(p=>(instant[keyOf(p)]||{}).ok).length;
    $("#scoreNum").textContent=ans; $("#scoreTot").textContent=tot; $("#scoreK").textContent="푼 문항 · 정답 "+ok;
    const pct=tot?Math.round(ans/tot*100):0;
    $("#gauge").innerHTML=WPUI.donut({pct,label:pct+"%",color:"var(--blue-600)",size:78,stroke:9,labelColor:"var(--blue-600)"}); }
}
/* 채점 결과를 화면에 반영한다. StaticDS·ApiDS 응답 형식이 같아서 한 벌로 쓴다.
   results[] = [{key, ok, chosen, answer_index, explanation}] */
function applyResults(results){
  (results||[]).forEach(r=>{
    const card=document.querySelector('.qcard[data-k="'+CSS.escape(r.key)+'"]'); if(!card) return;
    card.querySelectorAll(".opt").forEach(el=>{ const ci=+el.dataset.ci; el.classList.remove("sel");
      if(ci===r.answer_index) el.classList.add("correct");
      else if(ci===r.chosen) el.classList.add("wrong"); });
    const ex=card.querySelector(".expl"); if(!ex) return;
    ex.innerHTML='<span class="lbl">해설 (정답 '+(CIRC[r.answer_index]||'')+')</span>'
                 +mdb(r.explanation||"");
    ex.classList.add("show");
  });
}
function showScore(sc){
  const tot=sc.total|0, ok=sc.correct|0, pct=sc.pct|0;
  $("#scoreNum").textContent=ok; $("#scoreTot").textContent=tot; $("#scoreK").textContent="정답 · 점수 "+pct+"%";
  $("#gauge").innerHTML=WPUI.donut({pct,label:pct+"%",color:pct>=60?"var(--success)":"var(--danger)",size:78,stroke:9,labelColor:pct>=60?"var(--success-text)":"var(--danger-text)"});
}
async function grade(){
  if(mode!=="quiz") return;
  let res; try{ res=await DS.grade(curRound, answers); }catch(e){ res=null; }
  if(!res||!res.results){ toast("채점에 실패했습니다. 잠시 후 다시 시도해 주세요."); return; }
  graded=true; lastResults=res.results; applyResults(res.results);
  const sc=res.score||{correct:0,total:0,pct:0}; showScore(sc);
  toast(sc.total+"문항 중 "+sc.correct+"문항 정답 ("+sc.pct+"%)");

  /* 성적표로 가는 버튼을 사이드바에 붙인다.
     at_id 는 로그인 회원일 때만 온다(grade.php 가 mb_id 있을 때만 기록한다) —
     비로그인은 채점 결과가 남지 않으므로 성적표가 성립하지 않는다.
     점수만 보여주고 끝나지 않게 하는 것이 이 제품의 핵심이라 채점 직후가 가장 좋은 자리다. */
  if(res.at_id){
    const box=$("#rpLink");
    if(box){
      box.innerHTML='<a class="btn btn-blue btn-block" href="report.php?pd='
        +encodeURIComponent(PD)+'&at='+(res.at_id|0)+'">'
        +'<svg class="ic"><use href="#i-chart"></use></svg> 성적표 보기</a>'
        +'<div class="rp-hint">과목별 취약도 · 취약 개념 · 계속 틀리는 문제</div>';
      box.style.display="";
    }
  }
}
/* "정답 보기" = 전 문항 미응답 채점. 별도 경로를 두지 않는다. */
async function reveal(){
  if(mode!=="quiz") return;
  let res; try{ res=await DS.grade(curRound, {}); }catch(e){ res=null; }
  if(!res||!res.results){ toast("정답을 불러오지 못했습니다."); return; }
  graded=true;
  lastResults=res.results.map(r=>({...r, chosen:-1}));
  applyResults(lastResults);
}
function resetAll(){ answers={}; instant={}; graded=false; lastResults=null; page=0; saveAns(); render(); }   // saveAns 가 빈 값이면 지운다

function renderHome(list){
  let h='<div class="cat">';
  if(THEORY.length){
    h+='<div class="cat-card cat-theory"><h3><span class="icon-box sm soft"><svg class="ic ic-sm"><use href="#i-book"></use></svg></span> 이론 요약노트</h3><div class="cat-row">'
      +THEORY.map(t=>'<button class="catbtn" onclick="goTheory(\''+t.href+'\')"><svg class="ic ic-sm"><use href="#i-doc"></use></svg>'+esc(t.label)+'</button>').join("")
      +'</div></div>';
  }
  rounds().forEach(r=>{ const vids=VIDEOS[r]||[];
    h+='<div class="cat-card"><h3><span class="icon-box sm soft"><svg class="ic ic-sm"><use href="#i-clipboard"></use></svg></span> '+esc(r)+' 모의고사</h3>';
    h+='<div class="cat-videos">'+(vids.length ? vidButtons(r)
        : '<div class="vid-empty">영상 준비 중</div>')+'</div>';
    h+='<button class="btn btn-blue" onclick="goQuiz(\''+r+'\')">문제 풀기 <svg class="ic"><use href="#i-arrow-right"></use></svg></button></div>';
  });
  h+='</div>'; list.innerHTML=h;
}

/* iframe 대신 'include' 방식: 요약 HTML 을 fetch 해서 Shadow DOM 에 주입(스타일 격리).
   상대경로(assets/svg 등)는 theory/ 기준으로 보정, 내부 요약 링크는 다시 fetch 로 로드. */
/* fetch/iframe 없이: 구워넣은 window.THEORY_HTML 을 Shadow DOM 에 주입 → file://·서버 둘 다 동작. */
function loadTheory(href){
  const box=document.getElementById("tbody"); if(!box) return;
  const html=(window.THEORY_HTML||{})[href];
  const sh=box.shadowRoot||box.attachShadow({mode:"open"});
  if(!html){ sh.innerHTML='<div style="padding:26px;color:#c22638;font-family:sans-serif">이론 내용을 찾을 수 없습니다. (theory_content.js 업로드 확인)</div>'; return; }
  sh.innerHTML=html;
  /* 이론 본문 안의 도식도 문제집별 경로로 옮긴다.
     theory_content.js 는 빌드 시점에 `figs/...` 로 구워지는데, 정적 데이터가
     pd/<pd_id>/ 로 내려가면 그 상대경로가 /exam/figs/ 를 가리켜 깨진다. */
  if(DATA){
    sh.querySelectorAll('img[src]').forEach(im=>{
      const s=im.getAttribute("src")||"";
      if(s.startsWith("figs/")) im.setAttribute("src", DATA+s);
    });
  }
  sh.querySelectorAll('a[href]').forEach(a=>{ const h=a.getAttribute("href")||"";
    const m=h.match(/summary_[^"'\/]*\.html/);
    if(m){ a.addEventListener("click",ev=>{ ev.preventDefault(); curTheory="theory/"+m[0]; buildSub(); loadTheory(curTheory); window.scrollTo({top:0,behavior:"smooth"}); }); }
  });
}

/* 영상 항목은 객체({provider,id,label,...})라 onclick 문자열에 담지 않고
   (회차, 인덱스)로 참조한다. */
function openVidAt(round, i){ openVid((VIDEOS[round]||[])[i]); }
function vidButtons(round){
  const vids=VIDEOS[round]||[];
  return vids.map((v,i)=>{
    /* provider=link 는 새 창으로 나간다(내려받아 보는 검토용 링크).
       아이콘을 바꿔 "여기서 재생되지 않는다"를 눌러보기 전에 알 수 있게 한다. */
    const ext = v.provider==="link";
    return '<button onclick="openVidAt(\''+esc(round)+'\','+i+')"'
      + (ext?' title="새 창에서 열립니다 — 내려받아 보는 링크입니다"':'') + '>'
      + '<svg class="ic ic-sm"><use href="#i-'+(ext?'arrow-right':'play')+'"></use></svg>'
      + esc(v.label) + (ext?' <small>(링크)</small>':'') + '</button>';
  }).join("");
}
/* 이론 영상 — 과목 버튼 바로 밑에 한 개.
   회차 영상과 달리 THEORY 항목 안에 `vid` 로 실려 온다(build_check.theory_videos).
   링크가 없는 과목은 **아무것도 그리지 않는다** — 죽은 버튼을 만들지 않는 규칙은 여기도 같다. */
function curTheoryItem(){
  const h=curTheory||(THEORY[0]&&THEORY[0].href);
  return THEORY.find(x=>x.href===h)||null;
}
function openTheoryVid(){ const t=curTheoryItem(); if(t&&t.vid&&t.vid.id) openVid(t.vid); }
function theoryVidBar(){
  const t=curTheoryItem(), v=t&&t.vid;
  if(!v||!v.id) return "";
  /* provider=link 는 새 창으로 나간다 — 회차 영상의 규칙을 그대로 따른다. */
  const ext=v.provider==="link";
  return '<div class="theory-vid" style="margin:0 0 12px">'
    + '<button class="catbtn" onclick="openTheoryVid()"'
    + (ext?' title="새 창에서 열립니다 — 내려받아 보는 링크입니다"':'') + '>'
    + '<svg class="ic ic-sm"><use href="#i-'+(ext?'arrow-right':'play')+'"></use></svg>'
    + esc(v.label||"이론 강의") + (ext?' <small>(링크)</small>':'') + '</button></div>';
}
function renderVideos(){
  const box=$("#vidList");
  const has=(VIDEOS[curRound]||[]).length;
  box.innerHTML = (has ? vidButtons(curRound)
                       : '<div class="vid-empty">이 회차의 영상이 없습니다.</div>')
    /* 레벨이 부족해 가려진 것이 있으면 사실만 알린다. 라벨·링크는 서버가 주지 않는다 —
       "무슨 영상이 있는지"까지 알려주면 가린 의미가 절반 사라진다. */
    + (vidHidden ? '<div class="vid-empty">검토용 영상 ' + vidHidden
                 + '개는 권한이 있는 계정만 볼 수 있습니다.</div>' : '');
}

/* 레벨 제한 영상을 받아 VIDEOS 에 합친다.
   비로그인이면 서버가 빈 목록을 주므로 그냥 아무 일도 안 일어난다. */
async function loadPrivateVideos(){
  if(!API || !PD) return;
  try{
    const r=await fetch(API+"videos.php?pd="+encodeURIComponent(PD),{credentials:"same-origin"});
    const d=await r.json();
    if(!d || !d.ok) return;
    vidHidden = d.hidden|0;
    const it=d.items;
    if(it && typeof it==="object"){
      Object.keys(it).forEach(round=>{
        const add=it[round]||[];
        if(!add.length) return;
        VIDEOS[round]=(VIDEOS[round]||[]).concat(add);
        VIDEOS[round].sort((a,b)=>(a.part||0)-(b.part||0));
      });
    }
    renderVideos();
  }catch(e){ /* 영상은 부가 기능이다. 실패해도 문제풀이를 막지 않는다. */ }
}
/* {provider,id} 추상화를 유지한다 — 유튜브 정책 문제가 생기면 provider 를
   'vimeo'/'file' 로 바꾸고 여기 분기 한 줄만 늘리면 된다. 비용이 거의 0이라 지금 해둔다. */
function embedUrl(v){
  const id=encodeURIComponent(v.id||""), t=(v.sec|0)>0?("&start="+(v.sec|0)):"";
  if(v.provider==="vimeo") return "https://player.vimeo.com/video/"+id;
  if(v.provider==="file")  return v.id;
  /* 구글 드라이브 — **저자 검토 단계용**이다.
     ⚠ 운영에 쓰지 않는다: 드라이브는 조회 쿼터가 있어 사람이 몰리면
       "죄송합니다. 현재 이 파일을 볼 수 없습니다" 로 막힌다. 그리고 시작시간(sec)을 못 넘긴다.
     완성되면 youtube_map.json 의 provider 를 youtube 로 바꿔 다시 빌드한다 —
     videos.js 한 파일(수 KB)만 다시 올리면 끝난다. */
  if(v.provider==="drive") return "https://drive.google.com/file/d/"+id+"/preview";
  return "https://www.youtube-nocookie.com/embed/"+id+"?rel=0&autoplay=1"+t;
}
function openVid(v){
  if(!v||!v.id){ toast("영상이 아직 준비되지 않았습니다."); return; }

  /* ★ provider=link — embed 하지 않고 새 창으로 보낸다.
     저자 검토 단계의 실제 사용 방식이 "링크를 눌러 내려받아 각자 PC 에서 본다" 이므로
     네이버 마이박스·구글 드라이브·드롭박스 등 **어디든 링크만 있으면 된다.**
     서비스별 embed API·조회 쿼터·공유 정책을 신경 쓸 필요가 없어 이게 가장 튼튼하다.
     완성되면 youtube_map.json 의 provider 를 youtube 로 바꿔 재빌드한다. */
  if(v.provider==="link"){
    /* noopener 를 붙인다 — 새 창이 window.opener 로 우리 페이지를 조작할 수 있다.
       외부 저장소 링크라 신뢰 경계 밖이다. */
    window.open(v.id, "_blank", "noopener,noreferrer");
    return;
  }

  const box=$("#vbox");
  if(v.provider==="file"){
    box.innerHTML='<video controls autoplay style="width:100%;display:block"'
                 +' src="'+esc(v.id)+'"></video>';
  }else{
    box.innerHTML='<iframe src="'+esc(embedUrl(v))+'" style="width:100%;aspect-ratio:16/9;border:0;display:block"'
                 +' allow="accelerometer;autoplay;encrypted-media;picture-in-picture"'
                 +' allowfullscreen title="'+esc(v.label||"해설 영상")+'"></iframe>';
  }
  $("#vmodal").classList.add("show");
}
function closeVid(){ $("#vbox").innerHTML=""; $("#vmodal").classList.remove("show"); }
$("#vmodal").addEventListener("click",e=>{ if(e.target.id==="vmodal") closeVid(); });

/* 그림 확대는 두지 않는다(2026-08-31 결정) — 모달이 화면을 덮는 것에 비해
   얻는 게 적다는 판단이다. 도식은 카드 안에서 폭에 맞춰 줄여 보여주고,
   그래도 안 읽히면 그건 도식을 다시 그려야 할 문제다(확대로 덮을 일이 아니다).
   대신 Esc 로 영상 모달은 닫히게 둔다. */
document.addEventListener("keydown",e=>{
  if(e.key==="Escape" && $("#vmodal") && $("#vmodal").classList.contains("show")) closeVid();
});

/* ══ 사이드 카드 접기/펼치기 ══════════════════════════════════════════════
   채점현황·해설영상 카드가 항상 펼쳐져 있어 자리를 많이 먹는다.
   제목줄을 누르면 접힌다. 접은 상태는 문제집별로 기억한다 —
   매번 다시 접게 만들면 접는 기능이 없느니만 못하다. */
function foldCards(){
  document.querySelectorAll("#side .side-card").forEach((card,i)=>{
    const h=card.querySelector("h3");
    if(!h || h.dataset.fold) return;
    h.dataset.fold="1";
    h.setAttribute("role","button"); h.tabIndex=0;
    const cap=document.createElement("span"); cap.className="fold-caret"; cap.textContent="▾";
    h.appendChild(cap);
    const key="exam.fold."+PD+"."+i;
    const set=open=>{ card.classList.toggle("folded", !open); h.setAttribute("aria-expanded", open?"true":"false"); };
    let saved=null; try{ saved=localStorage.getItem(key); }catch(e){}
    set(saved!=="0");                                  // 저장된 값이 없으면 펼침
    const toggle=()=>{ const open=card.classList.contains("folded"); set(open);
      try{ localStorage.setItem(key, open?"1":"0"); }catch(e){} };
    h.addEventListener("click",toggle);
    h.addEventListener("keydown",e=>{ if(e.key==="Enter"||e.key===" "){ e.preventDefault(); toggle(); } });
  });
}
let tt; function toast(m){ const t=$("#toast"); t.textContent=m; t.classList.add("show"); clearTimeout(tt); tt=setTimeout(()=>t.classList.remove("show"),1900); }

/* 서버 모드에서 내 상태와 CSRF 를 받아둔다.
   grade.php 는 로그인 회원에게 CSRF 를 요구하므로 채점 전에 이게 끝나 있어야 한다.
   API 가 비면(file:// 정적 폴백) 아무것도 하지 않는다.
   ⚠ 헤더 계정칸 UI 는 S7 에서 붙인다. 지금은 데이터만 확보한다. */
async function loadMe(){
  if(!API) return;
  try{ window.ME = await DS.me(); }catch(e){ window.ME = {login:0}; }
}

/* ══ 과목게시판 ═══════════════════════════════════════════════════════════
 *
 * 그누보드 게시판(문제집당 1개, 말머리=과목)이 정본이고 여기는 **요약 뷰**다.
 * 게시판의 페이징·글쓰기·검색은 자기 URL 로 이동하므로 이 탭 안에 다 넣지 않는다 —
 * 최근 글을 보여주고 전체는 새 창으로 넘긴다.
 *
 * 데이터는 api/board.php 가 준다(로그인 없이도 목록은 보인다).
 * 과목 칩을 먼저 보여주는 게 핵심이다: 이용자는 "무슨 과목 몇 번"을 다 적기보다
 * 과목만 고르고 본문을 쓰는 쪽이 흔하다.
 */
let boardSj=0, boardCache={};

function renderBoard(list){
  const chips = '<div class="bd-chips">'
    + '<button class="'+(boardSj===0?'on':'')+'" data-sj="0">전체</button>'
    + SUBJECTS.map(s=>'<button class="'+(boardSj===s.sj_no?'on':'')+'" data-sj="'+s.sj_no+'">'
        +esc(s.sj_name)+'</button>').join("")
    + '</div>';

  const d = boardCache[boardSj];
  let body;
  if(!d){
    body = '<div class="empty">불러오는 중…</div>';
  }else if(!d.ok){
    /* ★ 실패 이유를 갈라 보여준다. 전부 "불러오지 못했습니다" 로 뭉치면
       게시판이 없는 것과 쿼리가 깨진 것을 구분할 수 없다 — 후자는 코드 고장이라
       운영자가 알아야 할 것이 완전히 다르다. */
    var hint = "";
    if (d.err === "no_board")
      hint = '이 문제집의 게시판이 아직 만들어지지 않았습니다.';
    else if (d.err === "board_query_failed")
      hint = '게시판 테이블을 읽지 못했습니다' + (d.table ? ' ('+esc(d.table)+')' : '')
           + '. 관리자에게 알려 주세요.';
    body = '<div class="empty">게시판을 불러오지 못했습니다.'
         + (hint ? '<br><small>'+hint+'</small>' : '')
         + '</div>';
  }else if(!d.items||!d.items.length){
    body = '<div class="empty">아직 글이 없습니다. 첫 질문을 남겨보세요.</div>';
  }else{
    body = '<div class="bd-list">' + d.items.map(it=>
      '<a class="bd-row" href="'+esc(it.href)+'" target="_blank" rel="noopener">'
      + '<span class="bd-sj">'+esc(it.category||"기타")+'</span>'
      + '<span class="bd-t">'+esc(it.subject)
      +   (it.replies?' <em>['+it.replies+']</em>':'')
      +   (it.answered?' <span class="bd-ok">답변완료</span>':'')
      + '</span>'
      + '<span class="bd-m">'+esc(it.name)+' · '+esc(it.date)+'</span></a>'
    ).join("") + '</div>';
  }

  const more = d && d.ok && d.board_url
    ? '<div class="bd-acts">'
      + '<a class="btn btn-blue" href="'+esc(d.write_url)+'" target="_blank" rel="noopener">질문하기</a>'
      + '<a class="btn btn-outline" href="'+esc(d.board_url)+'" target="_blank" rel="noopener">전체 보기</a>'
      + '</div>'
    : '';

  list.innerHTML = chips + body + more;

  list.querySelectorAll(".bd-chips button").forEach(b=>b.onclick=()=>{
    boardSj=+b.dataset.sj; render(); loadBoard();
  });

  if(!d) loadBoard();
}

function loadBoard(){
  if(boardCache[boardSj]) return;
  if(!API){ boardCache[boardSj]={ok:0, err:"no_api"}; render(); return; }
  const sj=boardSj;
  fetch(API+"board.php?pd="+encodeURIComponent(PD)+"&sj="+sj,{credentials:"same-origin"})
    .then(r=>r.json())
    .then(d=>{ boardCache[sj]=d; if(sj===boardSj) render(); })
    .catch(()=>{ boardCache[sj]={ok:0}; if(sj===boardSj) render(); });
}

/* ══ 부팅 ═════════════════════════════════════════════════════════════════ */

function buildFilters(){
  /* 과목 드롭다운을 다시 채운다. DS.problems() 로 P 가 갈리면 다시 불러야 한다.
     ★ 난이도 필터는 뺐다 — 난이도는 집필 쪽 표기이고, 응시자가 「하만 풀기」로
       쓰는 순간 모의고사가 아니게 된다. 카드의 난이도 칩은 그대로 둔다. */
  const sub=$("#fSubject");
  if(!sub) return;
  sub.innerHTML='<option value="">전체 과목</option>';
  subjectNames().forEach(s=>{ const o=document.createElement("option"); o.value=s; o.textContent=s; sub.appendChild(o); });
}

(async function(){
  /* me 를 먼저 기다린다. grade.php 가 로그인 회원에게 CSRF 를 요구하므로
     채점 버튼이 눌리기 전에 ME 가 채워져 있어야 한다. */
  await loadMe();

  /* ★ 문제를 서버에서 받는다. 예전에는 ApiDS.problems 가 호출되지 않아
     관리자에서 고친 문제가 화면에 반영되지 않았다(구워진 problems.js 만 읽었다). */
  try{
    const d=await DS.problems(0);          // 0 = 전 회차
    if(d&&d.problems&&d.problems.length) P=d.problems;
    if(d&&d.subjects) SUBJECTS=d.subjects;
    if(d&&d.rounds)   ROUNDS=d.rounds;
    if(d&&d.product&&d.product.pd_name) PD_NAME=d.product.pd_name;
  }catch(e){ /* 정적 폴백 유지 — window.PROBLEMS 로 계속 돈다 */ }

  buildFilters();
  /* 필터를 바꿔도 답안은 지우지 않는다 — 과목만 좁혀 봤는데 풀던 게 날아가면 안 된다.
     채점 상태(graded)만 초기화해 새 범위로 다시 채점하게 한다. */
  ["#fSubject"].forEach(s=>{ const el=$(s); if(el) el.onchange=()=>{ graded=false; lastResults=null; page=0; render(); }; });
  document.querySelectorAll("#modes button").forEach(b=>b.onclick=()=>setMode(b.dataset.m));

  /* ?m= · ?rd= 를 읽는다. 헤더의 '이론' 메뉴가 &m=theory 를 넘기는데
     예전에는 무시하고 항상 홈으로 떨어졌다. */
  const qs=new URLSearchParams(location.search);
  const rs=rounds();
  const wantRd=qs.get("rd");
  curRound = (wantRd && rs.includes(wantRd)) ? wantRd : (rs[0]||null);
  curTheory=(THEORY[0]&&THEORY[0].href)||null;

  let m=qs.get("m")||"home";
  if(m==="round"||m==="rounds") m="quiz";       // 옛 링크 호환
  if(MODES.indexOf(m)<0) m="home";
  // 문제가 0건이면 문제집 탭으로 보내지 않는다 — 눌러도 빈 화면이다
  if(m==="quiz" && !rs.length) m="home";

  setMode(m); renderVideos(); foldCards();

  /* 레벨 제한 영상은 나중에 합친다 — 첫 화면을 기다리게 하지 않는다. */
  loadPrivateVideos();
})();
