const adminState = {
  key: sessionStorage.getItem("nimang-admin-key") || "",
  settings: null,
  message: "",
};

const adminApp = document.querySelector("#adminApp");

function escapeHtml(value = "") {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

async function adminFetch(path, options = {}) {
  const headers = { "X-Admin-Key": adminState.key, ...(options.headers || {}) };
  if (options.body) headers["Content-Type"] = "application/json";
  const response = await fetch(path, { ...options, headers });
  if (options.raw) {
    if (!response.ok) {
      const payload = await response.json().catch(() => ({}));
      throw new Error(payload.error || "导出失败。");
    }
    return response;
  }
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(payload.message || payload.error || "请求失败。");
  return payload;
}

function page(content) {
  adminApp.innerHTML = `
    <header class="admin-header">
      <div class="admin-brand"><img src="/assets/brand/logo-header.png" alt="逆芒营销" /><h1>操作助手后台</h1></div>
      <a href="/">返回员工登录页</a>
    </header>
    <main class="admin-main">${content}</main>
  `;
}

function renderLogin(message = "") {
  page(`
    <section class="admin-auth">
      <h2>后台身份验证</h2>
      <p>请输入服务器启动时配置的操作助手密钥。</p>
      <form class="admin-row" id="adminLoginForm">
        <label>管理员密钥<input class="control" type="password" name="key" autocomplete="current-password" required /></label>
        <button class="button button--primary" type="submit">进入后台</button>
      </form>
      <div class="admin-message">${escapeHtml(message)}</div>
    </section>
  `);
}

function renderDashboard() {
  const settings = adminState.settings;
  page(`
    <div class="admin-stats">
      <div><span>当前实验场次</span><strong>${escapeHtml(settings.scene_code)}</strong></div>
      <div><span>员工账号</span><strong>${settings.accounts}</strong></div>
      <div><span>已创建团队任务</span><strong>${settings.sessions}</strong></div>
      <div><span>已提交订单</span><strong>${settings.submissions}</strong></div>
      <div><span>问卷回答记录</span><strong>${settings.survey_responses}</strong></div>
    </div>

    <section class="admin-section">
      <h2>实验场次设置</h2>
      <p>新创建的团队任务将自动关联当前场次编号，已有数据不会被改写。</p>
      <form class="admin-row" id="sceneForm">
        <label>当前场次编号<input class="control" name="scene_code" value="${escapeHtml(settings.scene_code)}" maxlength="14" required /></label>
        <button class="button button--primary" type="submit">更新场次编号</button>
      </form>
    </section>

    <section class="admin-section">
      <h2>数据导出</h2>
      <p>CSV 文件采用 UTF-8 with BOM 编码，选择依据备注中的中文、标点与换行会完整保留。</p>
      <div class="admin-actions">
        <button class="button button--secondary" data-export="all">导出全部操作记录</button>
        <button class="button button--secondary" data-export="performance">导出绩效汇总</button>
        <button class="button button--secondary" data-export="survey">导出内嵌问卷记录</button>
        <button class="button button--secondary" data-export="scene">导出当前场次数据</button>
        <button class="button button--secondary" data-export="team">导出指定团队操作记录</button>
      </div>
      <div class="admin-row" style="margin-top:12px">
        <label>指定团队编号<input class="control" id="exportTeam" placeholder="如：G1" maxlength="14" /></label>
      </div>
    </section>

    <section class="admin-section danger-zone">
      <h2>测试数据重置</h2>
      <p>仅用于预测试或正式实验开始前清理指定团队批次。重置会删除该任务下的登录、订单和绩效记录。</p>
      <form class="admin-row" id="resetForm">
        <label>团队编号<input class="control" name="team_code" placeholder="如：G1" maxlength="4" required /></label>
        <label>任务批次
          <select class="control" name="batch_id" required>
            <option value="practice_a">练习任务A</option>
            <option value="practice_b">练习任务B</option>
            <option value="round_1">团队推广任务A</option>
            <option value="round_2">团队推广任务B</option>
          </select>
        </label>
        <button class="button" type="submit">重置指定数据</button>
      </form>
    </section>
    <div class="admin-message" role="status">${escapeHtml(adminState.message)}</div>
  `);
}

async function loadDashboard() {
  try {
    adminState.settings = await adminFetch("/api/admin/settings");
    sessionStorage.setItem("nimang-admin-key", adminState.key);
    renderDashboard();
  } catch (error) {
    adminState.key = "";
    sessionStorage.removeItem("nimang-admin-key");
    renderLogin(error.message);
  }
}

async function downloadExport(type) {
  let path = `/api/admin/export?type=${encodeURIComponent(type)}`;
  if (type === "team") {
    const team = document.querySelector("#exportTeam").value.trim().toUpperCase();
    if (!team) throw new Error("请先填写要导出的团队编号。");
    path += `&team=${encodeURIComponent(team)}`;
  }
  const response = await adminFetch(path, { raw: true });
  const blob = await response.blob();
  const disposition = response.headers.get("Content-Disposition") || "";
  const filename = disposition.match(/filename="([^"]+)"/)?.[1] || "experiment_data.csv";
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
  adminState.message = `已生成 ${filename}`;
  renderDashboard();
}

document.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (event.target.id === "adminLoginForm") {
    adminState.key = new FormData(event.target).get("key");
    await loadDashboard();
    return;
  }
  if (event.target.id === "sceneForm") {
    try {
      const scene_code = new FormData(event.target).get("scene_code").trim().toUpperCase();
      await adminFetch("/api/admin/settings", { method: "POST", body: JSON.stringify({ scene_code }) });
      adminState.message = "场次编号已更新。";
      await loadDashboard();
    } catch (error) {
      adminState.message = error.message;
      renderDashboard();
    }
    return;
  }
  if (event.target.id === "resetForm") {
    const payload = Object.fromEntries(new FormData(event.target));
    payload.team_code = payload.team_code.trim().toUpperCase();
    if (!window.confirm(`确认删除 ${payload.team_code} 的所选任务数据吗？此操作不能撤销。`)) return;
    try {
      await adminFetch("/api/admin/reset", { method: "POST", body: JSON.stringify(payload) });
      adminState.message = `${payload.team_code} 的指定任务数据已重置。`;
      await loadDashboard();
    } catch (error) {
      adminState.message = error.message;
      renderDashboard();
    }
  }
});

document.addEventListener("click", async (event) => {
  const type = event.target.closest("[data-export]")?.dataset.export;
  if (!type) return;
  try {
    await downloadExport(type);
  } catch (error) {
    adminState.message = error.message;
    renderDashboard();
  }
});

if (adminState.key) loadDashboard();
else renderLogin();
