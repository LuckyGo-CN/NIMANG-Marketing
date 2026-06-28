const MEMBERS = ["01", "02", "03", "04"].map((id) => ({ id, name: `推广专员${id}` }));

const state = {
  accountToken: localStorage.getItem("nimang-account-token") || "",
  taskToken: localStorage.getItem("nimang-task-token") || "",
  activeStep: localStorage.getItem("nimang-active-step") || "",
  workbench: null,
  data: null,
  view: "login",
  filter: "all",
  activeOrderId: null,
  serverOffset: 0,
  submitting: false,
  draft: null,
  surveyModule: "",
  surveyStartedAt: "",
};

const app = document.querySelector("#app");

function resetScroll() {
  window.requestAnimationFrame(() => window.scrollTo({ top: 0, left: 0, behavior: "instant" }));
}

function escapeHtml(value = "") {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

async function api(path, options = {}, auth = "account") {
  const headers = { "Content-Type": "application/json", ...(options.headers || {}) };
  const token = auth === "task" ? state.taskToken : state.accountToken;
  if (token) headers.Authorization = `Bearer ${token}`;
  let response;
  try {
    response = await fetch(path, { ...options, headers });
  } catch {
    throw new Error("无法连接系统服务器，请检查本地服务是否已启动。");
  }
  const payload = await response.json().catch(() => ({}));
  if (!response.ok || payload.success === false) {
    throw new Error(payload.message || payload.error || "系统请求失败，请稍后重试。");
  }
  return payload;
}

function brand(kind = "header") {
  const source = kind === "login" ? "/assets/brand/logo-login.png" : "/assets/brand/logo-header.png";
  return `<img class="brand-logo brand-logo--${kind}" src="${source}" alt="逆芒营销 NIMANG" />`;
}

function renderLogin(message = "") {
  state.view = "login";
  app.innerHTML = `
    <main class="login-screen login-screen--workflow">
      <section class="login-panel">
        <div class="login-card workflow-login-card">
          ${brand("login")}
          <div class="login-title-block">
            <span>推广业务中心</span>
            <h1>推广订单处理系统</h1>
            <p>登录后进入个人工作台，按流程完成当前任务</p>
          </div>
          <form id="loginForm" novalidate>
            <label class="field-label" for="teamCode">团队编号</label>
            <input class="control" id="teamCode" name="team_code" placeholder="请输入团队编号，如G1" maxlength="4" autocomplete="off" required />
            <label class="field-label" for="memberId">员工身份</label>
            <select class="control" id="memberId" name="member_id" required>
              <option value="" selected disabled>请选择员工身份</option>
              ${MEMBERS.map((member) => `<option value="${member.name}">${member.name}</option>`).join("")}
            </select>
            <div class="form-message" role="alert">${escapeHtml(message)}</div>
            <button class="button button--primary button--wide" type="submit">进入工作台</button>
          </form>
          <p class="support-note">如需协助，请联系操作助手</p>
        </div>
      </section>
      <section class="login-showcase login-showcase--workflow" aria-hidden="true">
        <div class="showcase-copy">
          <span class="showcase-kicker">NIMANG WORKSPACE</span>
          <h2>清晰的任务进度<br />顺畅的团队协作</h2>
          <p>订单处理、安排确认与绩效结果均在同一工作台内完成。</p>
        </div>
        <div class="showcase-board">
          <div class="showcase-board__top"><i></i><i></i><i></i><span>今日工作流</span></div>
          <div class="showcase-board__body">
            <div class="mock-sidebar"><b></b><b></b><b></b><b></b></div>
            <div class="mock-flow"><span></span><span></span><span></span><span></span></div>
          </div>
        </div>
      </section>
    </main>
  `;
  resetScroll();
}

function accountHeader({ compact = false } = {}) {
  const data = state.workbench || state.data;
  return `
    <header class="workspace-header ${compact ? "workspace-header--compact" : ""}">
      <a class="workspace-brand" href="#" data-action="workbench">${brand("header")}<span>推广订单处理系统</span></a>
      <div class="workspace-account">
        <div><strong>${escapeHtml(data?.team_code || "")}-${escapeHtml(data?.member_id || "")}</strong><small>${escapeHtml(data?.member_name || "")}</small></div>
        <button class="icon-text-button" data-action="logout" title="退出登录">退出</button>
      </div>
    </header>
  `;
}

const STATUS_LABELS = {
  completed: "已完成",
  current: "进行中",
  waiting_assistant: "等待操作助手",
  locked: "未开始",
};

function stepButton(step) {
  if (step.status === "locked" || step.status === "waiting_assistant") {
    return `<button class="button button--small" disabled>${step.status === "waiting_assistant" ? "等待中" : "尚未解锁"}</button>`;
  }
  if (step.status === "completed" && step.kind !== "performance") {
    return `<button class="button button--small button--complete" disabled>已完成</button>`;
  }
  const labels = { task: "进入任务", survey: "填写问卷", performance: "查看结果" };
  return `<button class="button button--small ${step.status === "current" ? "button--primary" : "button--secondary"}" data-step="${step.key}">${labels[step.kind] || "查看"}</button>`;
}

function renderWorkbench() {
  state.view = "workbench";
  state.data = null;
  const data = state.workbench;
  const percentage = Math.round((data.completed_count / data.total_count) * 100);
  app.innerHTML = `
    <main class="workspace-shell">
      ${accountHeader()}
      <div class="workspace-main">
        <aside class="workspace-nav">
          <div class="nav-title">工作空间</div>
          <button class="workspace-nav__item is-active"><span>▦</span>任务工作台</button>
          <div class="nav-divider"></div>
          <div class="nav-meta"><span>任务编号</span><strong>${escapeHtml(data.participant_uid)}</strong></div>
          <div class="nav-help"><strong>遇到问题？</strong><span>请暂停操作并联系操作助手。</span></div>
        </aside>
        <section class="workbench-content">
          <div class="workbench-heading">
            <div><span class="eyebrow">员工工作流</span><h1>推广订单处理工作台</h1><p>按照当前流程依次完成任务，已提交内容会自动保存。</p></div>
            <div class="stage-summary"><span>当前阶段</span><strong>${escapeHtml(data.current_stage)}</strong></div>
          </div>
          <section class="identity-strip">
            <div><span>团队编号</span><strong>${escapeHtml(data.team_code)}</strong></div>
            <div><span>员工身份</span><strong>${escapeHtml(data.member_name)}</strong></div>
            <div class="identity-progress"><span>整体进度 <b>${data.completed_count}/${data.total_count}</b></span><div><i style="width:${percentage}%"></i></div></div>
          </section>
          <section class="workflow-panel">
            <div class="section-heading"><div><h2>我的任务流</h2><p>仅当前节点可进入，完成后自动解锁下一步。</p></div><span>${percentage}% 已完成</span></div>
            <div class="workflow-list">
              ${data.steps.map((step) => `
                <article class="workflow-step workflow-step--${step.status}">
                  <div class="workflow-rail"><span>${step.status === "completed" ? "✓" : step.index}</span><i></i></div>
                  <div class="workflow-step__content">
                    <div class="workflow-step__text"><div><span class="step-status">${STATUS_LABELS[step.status]}</span><h3>${escapeHtml(step.label)}</h3></div><p>${escapeHtml(step.description)}</p></div>
                    ${stepButton(step)}
                  </div>
                </article>
              `).join("")}
            </div>
          </section>
        </section>
      </div>
    </main>
  `;
  resetScroll();
}

async function loadWorkbench(message = "") {
  if (!state.accountToken) return renderLogin(message);
  try {
    state.workbench = await api("/api/workbench");
    renderWorkbench();
  } catch (error) {
    localStorage.removeItem("nimang-account-token");
    state.accountToken = "";
    renderLogin(error.message);
  }
}

function formatCountdown(target) {
  if (!target) return "--:--";
  const now = Date.now() / 1000 + state.serverOffset;
  const seconds = Math.max(0, Math.ceil(target - now));
  return `${String(Math.floor(seconds / 60)).padStart(2, "0")}:${String(seconds % 60).padStart(2, "0")}`;
}

function taskShell(content, active = "service") {
  const data = state.data;
  return `
    <main class="app-shell">
      <header class="task-header">
        <div class="task-header__brand">${brand("header")}<span>${escapeHtml(data.batch_label)}</span></div>
        <div class="task-header__timer"><span>${data.started_at ? "剩余处理时间" : "等待团队成员"}</span><strong id="taskTimer">${formatCountdown(data.end_at)}</strong></div>
        <div class="task-header__account"><span>${escapeHtml(data.team_code)}-${escapeHtml(data.member_id)}</span><button data-action="workbench">返回工作台</button></div>
      </header>
      <nav class="task-nav">
        <button class="${active === "service" ? "is-active" : ""}" data-action="service">推广服务</button>
        <button class="${active === "overview" ? "is-active" : ""}" data-action="overview">订单总览</button>
      </nav>
      <section class="task-content">${content}</section>
    </main>
  `;
}

function renderMatching() {
  state.view = "matching";
  const data = state.data;
  app.innerHTML = taskShell(`
    <section class="matching-page">
      <div class="matching-spinner"><span></span><span></span><span></span></div>
      <h1>${data.batch_id === "practice_b" ? "正在准备个人练习" : "正在匹配团队成员"}</h1>
      <p>已就绪 ${data.joined_count} / ${data.required_count}，成员到齐后系统将自动开始计时。</p>
      <div class="member-ready-list">${data.members.map((member) => `<div class="${member.joined ? "is-ready" : ""}"><span>${member.joined ? "✓" : "·"}</span>${escapeHtml(member.name)}<b>${member.joined ? "已就绪" : "待加入"}</b></div>`).join("")}</div>
      <button class="button button--secondary" data-action="workbench">返回工作台</button>
    </section>
  `);
  resetScroll();
}

function orderCounts() {
  const total = state.data.orders.length;
  const done = state.data.orders.filter((order) => order.submitted).length;
  return { total, done, todo: total - done };
}

function productCard(order) {
  const label = order.submitted ? (state.data.is_practice ? "查看研判结果" : "查看已提交方案") : "设置推广方案";
  return `
    <article class="product-card">
      <div class="product-card__top"><strong>${escapeHtml(order.id)}</strong><span class="status-chip ${order.submitted ? "status-chip--done" : "status-chip--todo"}">${order.submitted ? "已提交" : "待处理"}</span></div>
      <div class="product-card__body"><div class="product-thumb"><img src="${escapeHtml(order.image)}" alt="${escapeHtml(order.name)}" /></div><div class="product-meta"><small>${escapeHtml(order.brand)}</small><h3>${escapeHtml(order.name)}</h3><span>${escapeHtml(order.category)}</span><strong>¥ ${order.price}</strong></div></div>
      <button class="button ${order.submitted ? "button--secondary" : "button--primary"} button--wide" data-order="${escapeHtml(order.id)}">${label}</button>
    </article>
  `;
}

function renderService() {
  state.view = "service";
  const counts = orderCounts();
  const filtered = state.data.orders.filter((order) => state.filter === "all" || (state.filter === "done" ? order.submitted : !order.submitted));
  app.innerHTML = taskShell(`
    <div class="page-heading"><h1>推广订单</h1><p>查看并处理分配给您的推广订单</p></div>
    <div class="order-toolbar"><div class="order-tabs"><button class="order-tab ${state.filter === "all" ? "is-active" : ""}" data-filter="all">全部订单 <span>${counts.total}</span></button><button class="order-tab ${state.filter === "todo" ? "is-active" : ""}" data-filter="todo">待处理 <span>${counts.todo}</span></button><button class="order-tab ${state.filter === "done" ? "is-active" : ""}" data-filter="done">已提交 <span>${counts.done}</span></button></div></div>
    <div class="product-grid">${filtered.length ? filtered.map(productCard).join("") : '<div class="empty-state">当前筛选条件下暂无订单</div>'}</div>
  `, "service");
  resetScroll();
}

function activeOrder() {
  return state.data.orders.find((order) => order.id === state.activeOrderId);
}

function orderInfo(order) {
  return `<aside class="order-info"><h2>订单信息</h2><dl><div><dt>订单编号</dt><dd>${escapeHtml(order.id)}</dd></div><div><dt>客户品牌</dt><dd>${escapeHtml(order.brand)}</dd></div><div><dt>产品名称</dt><dd>${escapeHtml(order.name)}</dd></div><div><dt>产品品类</dt><dd>${escapeHtml(order.category)}</dd></div><div><dt>产品定价</dt><dd>¥ ${order.price}</dd></div></dl><div class="detail-product-image"><img src="${escapeHtml(order.image)}" alt="${escapeHtml(order.name)}" /></div></aside>`;
}

function accountSuffix(value) {
  if (value === "头部达人") return "（10万+粉丝量级）";
  if (value === "腰部达人") return "（1-10万粉丝量级）";
  return "（< 1万粉丝量级）";
}

function optionRow(label, key, values) {
  return `<fieldset class="choice-row"><legend>${label}</legend><div class="choice-options">${values.map((value) => `<label class="choice-option"><input type="radio" name="${key}" value="${escapeHtml(value)}" ${state.draft[key] === value ? "checked" : ""} required /><span>${escapeHtml(value)}${key === "account_type" ? accountSuffix(value) : ""}</span></label>`).join("")}</div></fieldset>`;
}

function resetDraft() {
  state.draft = { gender: state.data.options.gender[0], age: state.data.options.age[0], account_type: state.data.options.account_type[0], format_type: state.data.options.format_type[0], reason_text: "" };
}

function renderSetup() {
  state.view = "setup";
  const order = activeOrder();
  const options = state.data.options;
  app.innerHTML = taskShell(`
    <button class="back-link" data-action="service">‹ 返回订单列表</button>
    <div class="detail-grid">${orderInfo(order)}<form class="plan-form" id="planForm"><h1>推广方案配置</h1>${optionRow("目标人群 - 性别", "gender", options.gender)}${optionRow("目标人群 - 年龄", "age", options.age)}${optionRow("种草账号类型", "account_type", options.account_type)}${optionRow("种草形式", "format_type", options.format_type)}<label class="reason-label" for="reasonText">选择依据备注 <span>（选填）</span></label><textarea id="reasonText" name="reason_text" maxlength="200" placeholder="如有需要，可简要记录您的判断依据">${escapeHtml(state.draft.reason_text)}</textarea><div class="character-count"><span id="reasonCount">${state.draft.reason_text.length}</span>/200</div><div class="form-message" id="planMessage" role="alert"></div><button class="button button--primary button--wide submit-plan" type="submit">提交推广方案</button></form></div>
  `, "service");
  resetScroll();
}

function renderWaiting() {
  state.view = "waiting";
  const order = activeOrder();
  app.innerHTML = taskShell(`<div class="waiting-page"><div class="spinner" aria-hidden="true"></div><h1>等待系统研判</h1><p>订单 ${escapeHtml(order.id)} 的推广方案已提交</p><div class="analysis-steps"><span class="is-active">匹配推广数据库</span><span>评估目标人群匹配度</span><span>评估账号与形式匹配度</span><span>生成订单研判结果</span></div></div>`, "service");
}

function planSummary(submission) {
  return `${submission.gender}，${submission.age}，${submission.account_type}，${submission.format_type}`;
}

function renderResult() {
  state.view = "result";
  const order = activeOrder();
  const submission = order.submission;
  let resultContent = "";
  if (state.data.is_practice && order.result?.kind === "practice_a") {
    resultContent = `<h1>${order.result.title}</h1><div class="submitted-plan"><strong>您的推广方案</strong><span>${escapeHtml(planSummary(submission))}</span><small>选择依据备注：${escapeHtml(submission.reason_text || "未填写")}</small></div><div class="result-metric">预估推广成功率 <strong>${order.result.success_rate}%</strong></div><h2>研判依据</h2><ul class="feedback-list">${order.result.items.map((item) => `<li><span>✓</span>${escapeHtml(item)}</li>`).join("")}</ul>`;
  } else if (state.data.is_practice) {
    resultContent = `<h1>${order.result.title}</h1><div class="submitted-plan"><strong>您的推广方案</strong><span>${escapeHtml(planSummary(submission))}</span><small>选择依据备注：${escapeHtml(submission.reason_text || "未填写")}</small></div><div class="trend-match">关键趋势匹配情况 <strong class="match-chip match-chip--${order.result.match_score}">${escapeHtml(order.result.match_label)}</strong></div><h2>趋势提示</h2><p>以下反馈仅针对本订单中与近期平台趋势相关的关键维度。</p><ul class="feedback-list">${order.result.items.map((item) => `<li><span>✓</span>${escapeHtml(item)}</li>`).join("")}</ul>`;
  } else {
    resultContent = `<h1>系统已完成研判</h1><div class="submitted-plan"><strong>已提交推广方案</strong><span>${escapeHtml(planSummary(submission))}</span><small>选择依据备注：${escapeHtml(submission.reason_text || "未填写")}</small></div><div class="formal-confirmation"><span>✓</span><div><strong>本次订单处理结果已记录</strong><p>正式任务期间不逐单显示成功率或研判依据。本轮任务结束后统一汇总个人与团队绩效。</p></div></div>`;
  }
  app.innerHTML = taskShell(`<div class="result-heading">${state.data.is_practice ? escapeHtml(order.result.title) : "推广方案记录"}</div><div class="detail-grid">${orderInfo(order)}<section class="result-panel">${resultContent}<button class="button button--primary button--wide" data-action="service">返回订单列表</button></section></div>`, "service");
}

function progressBar(member) {
  const percentage = Math.round((member.completed / member.total) * 100);
  return `<span class="progress-value">${member.completed}/${member.total}</span><span class="progress-track"><i style="width:${percentage}%"></i></span>`;
}

function renderOverview() {
  state.view = "overview";
  const data = state.data;
  const mine = data.members.find((member) => member.current);
  let content;
  if (data.is_practice) {
    content = `<div class="page-heading"><h1>订单总览</h1><p>练习任务完成进度</p></div><div class="practice-overview"><span>我的已完成订单</span><strong>${mine.completed}<small> / ${mine.total}</small></strong></div><button class="button button--primary practice-complete-button" data-action="complete-task">我已完成练习，返回工作台</button><p class="overview-footnote">练习任务用于熟悉系统操作与反馈规则，结果不计入正式任务绩效。</p>`;
  } else {
    const performance = data.performance;
    const teamCompleted = data.members.reduce((sum, member) => sum + member.completed, 0);
    const totalOrders = data.members.reduce((sum, member) => sum + member.total, 0);
    content = `<div class="page-heading"><h1>订单总览</h1></div><div class="overview-metrics"><div><span>我的已完成订单</span><strong>${mine.completed}<small> / ${mine.total}</small></strong></div><div><span>我的平均成功率</span><strong class="metric-text">${performance ? `${performance.personal_average}%` : "任务结束后显示"}</strong></div><div><span>团队已完成订单</span><strong>${teamCompleted}<small> / ${totalOrders}</small></strong></div><div><span>团队平均成功率</span><strong class="metric-text">${performance ? `${performance.team_average}%` : "任务结束后显示"}</strong></div></div><section class="team-progress"><h2>团队成员进度</h2><div class="progress-table"><div class="progress-row progress-row--head"><span>团队编号</span><span>成员身份</span><span>已完成订单</span><span>当前状态</span></div>${data.members.map((member) => `<div class="progress-row ${member.current ? "is-current" : ""}"><span>${escapeHtml(data.team_code)}</span><span>${escapeHtml(member.name)}${member.current ? "（我）" : ""}</span><span>${progressBar(member)}</span><span>${data.phase === "running" ? "处理中" : "任务已结束"}</span></div>`).join("")}</div></section><div class="data-note"><strong>数据说明</strong><span>正式任务期间不实时显示成功率，本轮结束后系统统一汇总个人与团队绩效。</span></div>`;
  }
  app.innerHTML = taskShell(content, "overview");
  if (!data.is_practice && data.phase.startsWith("ended")) renderEndModal();
}

function performanceTiles(performance) {
  return `<div class="performance-grid"><div><span>个人完成数量</span><strong>${performance.personal_completed}<small> / ${state.data.order_count}</small></strong></div><div><span>个人平均成功率</span><strong>${performance.personal_average}<small>%</small></strong></div><div><span>团队完成数量</span><strong>${performance.team_completed}<small> / ${state.data.order_count * state.data.required_count}</small></strong></div><div><span>团队平均成功率</span><strong>${performance.team_average}<small>%</small></strong></div></div>`;
}

function renderEndModal() {
  document.querySelector(".modal-layer")?.remove();
  const data = state.data;
  const waiting = data.phase === "ended_waiting";
  const layer = document.createElement("div");
  layer.className = "modal-layer";
  layer.innerHTML = `<section class="end-modal" role="dialog" aria-modal="true"><div class="end-icon">✓</div><h1>${escapeHtml(data.batch_label)}已结束</h1><div class="modal-info">本轮时间已结束，未提交订单记录为未完成，已提交订单不能修改。</div>${waiting ? `<p>请听从操作助手的指示，绩效将在倒计时结束后开放。</p><div class="reveal-timer"><span>绩效结果开放倒计时</span><strong id="revealTimer">${formatCountdown(data.performance_at)}</strong></div><button class="button button--primary button--wide" disabled>等待绩效结果</button>` : `<p>系统已汇总您和团队成员本轮提交的推广方案：</p>${performanceTiles(data.performance)}<button class="button button--primary button--wide" data-action="complete-task">我已记录，返回工作台</button>`}</section>`;
  document.body.appendChild(layer);
}

function renderPracticeEnded() {
  state.view = "practice-ended";
  app.innerHTML = taskShell(`<section class="practice-ended"><div class="end-icon">✓</div><h1>${escapeHtml(state.data.batch_label)}已结束</h1><p>本轮练习时间已结束，系统已锁定订单提交。</p><button class="button button--primary" data-action="complete-task">我已完成练习，返回工作台</button></section>`, "overview");
}

function renderTaskCurrent() {
  if (!state.data) return;
  if (state.data.phase === "waiting") return renderMatching();
  if (state.data.phase.startsWith("ended") && state.data.is_practice) return renderPracticeEnded();
  if (state.data.phase.startsWith("ended") && !state.data.is_practice) return renderOverview();
  if (state.view === "overview") return renderOverview();
  if (state.view === "setup") return renderSetup();
  if (state.view === "waiting") return renderWaiting();
  if (state.view === "result") return renderResult();
  renderService();
}

async function refreshTask({ preserveForm = false } = {}) {
  if (!state.taskToken) return;
  try {
    const previousPhase = state.data?.phase;
    const data = await api("/api/state", {}, "task");
    state.data = data;
    state.serverOffset = data.server_time - Date.now() / 1000;
    if (data.phase === "waiting") state.view = "matching";
    if (previousPhase === "waiting" && data.phase === "running") state.view = "service";
    if (data.phase.startsWith("ended")) state.view = data.is_practice ? "practice-ended" : "overview";
    if (!(preserveForm && state.view === "setup" && data.phase === "running")) renderTaskCurrent();
  } catch {
    clearActiveTask();
    await loadWorkbench();
  }
}

function clearActiveTask() {
  state.taskToken = "";
  state.activeStep = "";
  state.data = null;
  state.activeOrderId = null;
  localStorage.removeItem("nimang-task-token");
  localStorage.removeItem("nimang-active-step");
  document.querySelector(".modal-layer")?.remove();
}

async function enterTask(stepKey) {
  const result = await api("/api/task/enter", { method: "POST", body: JSON.stringify({ step_key: stepKey }) });
  state.taskToken = result.task_token;
  state.activeStep = stepKey;
  state.view = "service";
  localStorage.setItem("nimang-task-token", state.taskToken);
  localStorage.setItem("nimang-active-step", state.activeStep);
  await refreshTask();
}

function surveyPageStart(moduleName) {
  const key = `nimang-survey-start-${state.workbench.participant_uid}-${moduleName}`;
  let value = sessionStorage.getItem(key);
  if (!value) {
    value = new Date().toISOString();
    sessionStorage.setItem(key, value);
  }
  return value;
}

function matrixQuestion(title, prefix, rows, columns) {
  const header = columns.map((column) => `<th scope="col">${escapeHtml(column)}</th>`).join("");
  const body = rows.map(([key, label]) => {
    const name = `${prefix}.${key}`;
    const cells = columns.map((column) => `<td><input type="radio" name="${escapeHtml(name)}" value="${escapeHtml(column)}" required /></td>`).join("");
    return `<tr><th scope="row">${escapeHtml(label)}</th>${cells}</tr>`;
  }).join("");
  return `<fieldset class="survey-question matrix-question"><legend>${escapeHtml(title)}</legend><div class="survey-matrix"><table><thead><tr><th class="survey-matrix__stub" scope="col"></th>${header}</tr></thead><tbody>${body}</tbody></table></div></fieldset>`;
}

function choiceQuestion(title, name, choices) {
  return `<fieldset class="survey-question"><legend>${title}</legend><div class="survey-choices">${choices.map((choice) => `<label><input type="radio" name="${name}" value="${escapeHtml(choice)}" required /><span>${escapeHtml(choice)}</span></label>`).join("")}</div></fieldset>`;
}

function renderSurvey(moduleName) {
  state.view = "survey";
  state.surveyModule = moduleName;
  state.surveyStartedAt = surveyPageStart(moduleName);
  const rows = [["home", "家居日用类"], ["beauty", "美妆护肤类"], ["outdoor", "运动户外类"]];
  let title = "";
  let intro = "";
  let questions = "";
  let submitLabel = "完成并返回工作台";
  if (moduleName === "round1_arrangement") {
    title = "任务安排确认A";
    intro = "请根据刚才阅读的上岗培训材料和练习任务反馈，确认您对本轮任务中推广方案判断规则的理解。";
    submitLabel = "已完成任务安排确认A，返回工作台";
    questions = matrixQuestion("请根据平台推广趋势反馈，为每个产品品类选择最合适的推广人群性别。[矩阵量表]", "gender", rows, ["不限", "男", "女"]) + matrixQuestion("请根据平台推广趋势反馈，为每个产品品类选择最合适的推广人群年龄。[矩阵量表]", "age", rows, ["18 - 24岁", "25 - 34岁", "35岁以上"]) + matrixQuestion("请根据平台推广趋势反馈，为每个产品品类选择最合适的种草账号类型。[矩阵量表]", "account", rows, ["头部达人 (10万+粉丝量级)", "腰部达人 (1 - 10万粉丝量级)", "素人博主 (<1万粉丝量级)"]) + matrixQuestion("请根据平台推广趋势反馈，为每个产品品类选择最合适的种草形式。[矩阵量表]", "format", rows, ["图文描述", "视频展示", "直播销售"]);
  } else if (moduleName === "round2_arrangement") {
    title = "任务安排确认B";
    intro = "请根据刚才了解的团队推广工作安排，确认以下信息并回答相关问题。";
    submitLabel = "已完成任务安排确认B，返回工作台";
    questions = choiceQuestion("1. 我在当前团队中的身份是：[单选]", "identity", ["我是刚加入团队的新成员", "我是当前团队的原有成员"]) + choiceQuestion("2. 我清楚，在本轮任务中，团队新成员与原有成员之间的任务报酬关系是：[单选]", "pay_relation", ["新成员本轮任务报酬低于原有成员", "新成员本轮任务报酬与原有成员相同", "新成员本轮任务报酬高于原有成员"]) + matrixQuestion("请根据您目前在这里的整体体验，指出您对以下陈述的同意程度。[矩阵量表]", "fairness", [["1", "1. 总的来说，我在这里受到了公平对待。"], ["2", "2. 总的来说，这里的安排对我很公平。"], ["3", "3. 总的来说，我相信我在这里受到了公平的待遇。"], ["4", "4. 当我谈论我的团队时，我通常会说“我们”而不是“他们”。"], ["5", "5. 我的团队的成功就是我的成功。"], ["6", "6. 当有人称赞我的团队时，我会感到这是一种个人的赞美。"]], ["非常不同意", "不同意", "有点不同意", "中立", "有点同意", "同意", "非常同意"]);
  } else {
    title = "近期趋势理解确认";
    intro = "请根据刚才阅读的培训材料和练习任务反馈，确认您对近期趋势的理解。";
    submitLabel = "已完成近期趋势理解，返回工作台";
    questions = choiceQuestion("1. 根据近期平台趋势反馈，在家居日用类产品中，哪一种草形式的推广效果有所提升？[单选]", "home_format", ["图文描述", "视频展示", "直播销售"]) + choiceQuestion("2. 根据近期平台趋势反馈，在美妆护肤类产品中，哪一种草账号类型的推广效果有所提升？[单选]", "beauty_account", ["头部达人", "腰部达人", "素人博主"]) + choiceQuestion("3. 根据近期平台趋势反馈，在运动户外类产品中，哪个年龄段用户的互动和转化表现有所提升？[单选]", "outdoor_age", ["18–24岁", "25–34岁", "35岁以上"]);
  }
  app.innerHTML = `<main class="workspace-shell">${accountHeader()}<section class="survey-page"><button class="back-link" data-action="workbench">‹ 返回工作台</button><div class="survey-heading"><div><span>任务安排</span><h1>${title}</h1><p>${intro}</p></div>${moduleName === "recent_trend" ? '<div class="survey-timer"><span>阅读时间</span><strong id="surveyTimer">03:00</strong><small id="surveyTimerNote">60 秒后可提交</small></div>' : ""}</div><form id="surveyForm" class="survey-form">${questions}<div class="survey-submit"><div class="form-message" id="surveyMessage"></div><button class="button button--primary" id="surveySubmit" type="submit" ${moduleName === "recent_trend" ? "disabled" : ""}>${submitLabel}</button></div></form></section></main>`;
  resetScroll();
  updateSurveyTimer();
}

function updateSurveyTimer() {
  if (state.view !== "survey" || state.surveyModule !== "recent_trend") return;
  const elapsed = Math.max(0, Math.floor((Date.now() - new Date(state.surveyStartedAt).getTime()) / 1000));
  const remaining = Math.max(0, 180 - elapsed);
  const timer = document.querySelector("#surveyTimer");
  const note = document.querySelector("#surveyTimerNote");
  const submit = document.querySelector("#surveySubmit");
  if (timer) timer.textContent = `${String(Math.floor(remaining / 60)).padStart(2, "0")}:${String(remaining % 60).padStart(2, "0")}`;
  if (elapsed >= 60) {
    if (submit) submit.disabled = false;
    if (note) note.textContent = remaining ? "可以提交" : "阅读时间已到";
  } else if (note) note.textContent = `${60 - elapsed} 秒后可提交`;
}

async function renderPerformance() {
  state.view = "performance";
  const payload = await api("/api/performance-history");
  await api("/api/workflow/complete", { method: "POST", body: JSON.stringify({ step_key: "performance" }) });
  app.innerHTML = `<main class="workspace-shell">${accountHeader()}<section class="performance-page"><button class="back-link" data-action="workbench">‹ 返回工作台</button><div class="performance-heading"><span>绩效结果</span><h1>个人与团队任务表现</h1><p>练习任务用于熟悉系统，正式任务结果按任务轮次汇总。</p></div><div class="history-list">${payload.records.map((record) => `<article class="history-card"><div class="history-card__title"><div><span>${record.is_practice ? "练习" : "正式任务"}</span><h2>${escapeHtml(record.batch_label)}</h2></div><b>${record.available ? "已汇总" : "暂无数据"}</b></div>${record.available ? `<div class="history-metrics"><div><span>个人完成</span><strong>${record.personal_completed}<small> / ${record.personal_total}</small></strong></div><div><span>个人平均成功率</span><strong>${record.personal_average}<small>%</small></strong></div>${record.is_practice ? "" : `<div><span>团队完成</span><strong>${record.team_completed}<small> / ${record.team_total}</small></strong></div><div><span>团队平均成功率</span><strong>${record.team_average}<small>%</small></strong></div>`}</div>` : '<p class="history-empty">尚未产生该任务记录。</p>'}</article>`).join("")}</div></section></main>`;
  resetScroll();
}

async function logout() {
  clearActiveTask();
  localStorage.removeItem("nimang-account-token");
  state.accountToken = "";
  state.workbench = null;
  renderLogin();
}

document.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (event.target.id === "loginForm") {
    const button = event.target.querySelector("button[type=submit]");
    button.disabled = true;
    button.textContent = "正在进入…";
    try {
      const result = await api("/api/account/login", { method: "POST", body: JSON.stringify(Object.fromEntries(new FormData(event.target))) });
      state.accountToken = result.token;
      localStorage.setItem("nimang-account-token", result.token);
      await loadWorkbench();
    } catch (error) {
      renderLogin(error.message);
    }
    return;
  }
  if (event.target.id === "planForm") {
    const payload = Object.fromEntries(new FormData(event.target));
    payload.order_id = state.activeOrderId;
    state.draft = { ...state.draft, ...payload };
    const message = document.querySelector("#planMessage");
    const button = event.target.querySelector("button[type=submit]");
    button.disabled = true;
    try {
      await api("/api/submit", { method: "POST", body: JSON.stringify(payload) }, "task");
      renderWaiting();
      window.setTimeout(async () => {
        await refreshTask();
        state.view = "result";
        renderResult();
      }, 1200);
    } catch (error) {
      if (message) message.textContent = error.message;
      button.disabled = false;
    }
    return;
  }
  if (event.target.id === "surveyForm") {
    const answers = Object.fromEntries(new FormData(event.target));
    const button = document.querySelector("#surveySubmit");
    const message = document.querySelector("#surveyMessage");
    button.disabled = true;
    try {
      await api("/api/questionnaire/submit", { method: "POST", body: JSON.stringify({ module_name: state.surveyModule, answers, page_start_time: state.surveyStartedAt }) });
      sessionStorage.removeItem(`nimang-survey-start-${state.workbench.participant_uid}-${state.surveyModule}`);
      await loadWorkbench();
    } catch (error) {
      message.textContent = error.message;
      button.disabled = false;
    }
  }
});

document.addEventListener("input", (event) => {
  if (event.target.id === "reasonText") {
    state.draft.reason_text = event.target.value;
    document.querySelector("#reasonCount").textContent = event.target.value.length;
  }
  if (event.target.matches("input[type=radio]") && state.draft) state.draft[event.target.name] = event.target.value;
});

document.addEventListener("click", async (event) => {
  const filter = event.target.closest("[data-filter]");
  if (filter) {
    state.filter = filter.dataset.filter;
    renderService();
    return;
  }
  const orderButton = event.target.closest("[data-order]");
  if (orderButton) {
    state.activeOrderId = orderButton.dataset.order;
    const order = activeOrder();
    if (order.submitted) renderResult();
    else { resetDraft(); renderSetup(); }
    return;
  }
  const stepButtonElement = event.target.closest("[data-step]");
  if (stepButtonElement) {
    const step = state.workbench.steps.find((item) => item.key === stepButtonElement.dataset.step);
    try {
      if (step.kind === "task") await enterTask(step.key);
      else if (step.kind === "survey") renderSurvey(step.target);
      else if (step.kind === "performance") await renderPerformance();
    } catch (error) {
      window.alert(error.message);
      await loadWorkbench();
    }
    return;
  }
  const action = event.target.closest("[data-action]")?.dataset.action;
  if (!action) return;
  if (action === "logout") return logout();
  if (action === "workbench") { clearActiveTask(); return loadWorkbench(); }
  if (action === "service" && state.data?.phase === "running") return renderService();
  if (action === "overview" && state.data) return renderOverview();
  if (action === "complete-task") {
    try {
      await api("/api/workflow/complete", { method: "POST", body: JSON.stringify({ step_key: state.activeStep }) });
      clearActiveTask();
      await loadWorkbench();
    } catch (error) {
      window.alert(error.message);
    }
  }
});

window.setInterval(() => {
  const timer = document.querySelector("#taskTimer");
  if (timer && state.data) timer.textContent = formatCountdown(state.data.end_at);
  const reveal = document.querySelector("#revealTimer");
  if (reveal && state.data) reveal.textContent = formatCountdown(state.data.performance_at);
  updateSurveyTimer();
}, 1000);

window.setInterval(() => {
  if (state.taskToken) refreshTask({ preserveForm: true });
  else if (state.accountToken && state.view === "workbench" && state.workbench?.steps.some((step) => step.status === "waiting_assistant")) loadWorkbench();
}, 2500);

if (state.taskToken && state.activeStep) refreshTask();
else if (state.accountToken) loadWorkbench();
else renderLogin();
