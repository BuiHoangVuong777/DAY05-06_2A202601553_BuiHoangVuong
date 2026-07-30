const state = {
  dashboard: null,
  tasksById: new Map(),
};

const $ = (selector) => document.querySelector(selector);

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

async function api(path, options = {}) {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    ...options,
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(data.error || `HTTP ${response.status}`);
  }
  return data;
}

function showToast(message, isError = false) {
  const toast = $("#toast");
  toast.textContent = message;
  toast.classList.toggle("error", isError);
  toast.classList.add("visible");
  window.clearTimeout(showToast.timeout);
  showToast.timeout = window.setTimeout(() => toast.classList.remove("visible"), 2800);
}

function localInputValue(iso) {
  if (!iso) return "";
  const date = new Date(iso);
  const local = new Date(date.getTime() - date.getTimezoneOffset() * 60_000);
  return local.toISOString().slice(0, 16);
}

function displayDate(iso) {
  if (!iso) return "Chưa có deadline";
  return new Intl.DateTimeFormat("vi-VN", {
    day: "2-digit",
    month: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(iso));
}

function taskCard(task) {
  const reasons = task.priority.reasons
    .slice(0, 3)
    .map((reason) => `<span class="reason-tag">${escapeHtml(reason)}</span>`)
    .join("");
  const source = task.source ? ` · ${escapeHtml(task.source)}` : "";
  const assignee = task.assignee || "Chưa giao";
  return `
    <article class="task-card level-${escapeHtml(task.priority.level)}">
      <i class="priority-marker" aria-hidden="true"></i>
      <div class="task-content">
        <div class="task-title-row">
          <strong title="${escapeHtml(task.title)}">${escapeHtml(task.title)}</strong>
          <span class="priority-score">P${task.priority.score}</span>
        </div>
        <div class="task-meta">
          <span>${escapeHtml(assignee)}</span>
          <span>·</span>
          <span>${displayDate(task.due_at)}${source}</span>
        </div>
        <div class="task-reasons">${reasons}</div>
        <div class="task-recommendation">💡 ${escapeHtml(task.priority.recommendation)}</div>
      </div>
      <div class="task-progress">
        <div class="progress-track"><i style="width:${Number(task.progress)}%"></i></div>
        <small>${Number(task.progress)}% hoàn thành</small>
        <button class="checkin-button" data-checkin="${task.id}" type="button">Cập nhật →</button>
      </div>
    </article>
  `;
}

function renderDashboard(data) {
  state.dashboard = data;
  state.tasksById = new Map(data.ranked_tasks.map((task) => [String(task.id), task]));

  $("#metric-active").textContent = data.summary.active;
  $("#metric-due").textContent = data.summary.due_today_or_overdue;
  $("#metric-alerts").textContent = data.summary.stuck_or_critical;
  $("#metric-completion").textContent = `${data.summary.completion_percent}%`;

  const active = data.ranked_tasks.filter((task) => task.status !== "done");
  $("#task-list").innerHTML = active.length
    ? active.map(taskCard).join("")
    : '<div class="empty-state">Team đã hoàn thành mọi task 🎉</div>';

  $("#discord-channel").textContent = data.discord_preview.channel.replace(/^#/, "");
  $("#discord-message").textContent = data.discord_preview.message;

  const weekly = data.weekly_unfinished.slice(0, 6);
  $("#weekly-list").innerHTML = weekly.length
    ? weekly
        .map(
          (task) => `
            <div class="weekly-item">
              <span>${escapeHtml(task.title)}</span>
              <strong>${Number(task.progress)}%</strong>
            </div>
          `,
        )
        .join("")
    : '<div class="empty-state">Không còn mục tiêu tồn.</div>';

  document.querySelectorAll("[data-checkin]").forEach((button) => {
    button.addEventListener("click", () => openCheckin(button.dataset.checkin));
  });
}

async function loadDashboard() {
  try {
    const data = await api("/api/dashboard");
    renderDashboard(data);
  } catch (error) {
    $("#task-list").innerHTML = `<div class="empty-state">${escapeHtml(error.message)}</div>`;
    showToast(error.message, true);
  }
}

async function loadHealth() {
  try {
    const health = await api("/api/health");
    const badge = $("#ai-status");
    if (health.ai_configured) {
      badge.textContent = `AI thật · ${health.ai_model}`;
      badge.classList.remove("fallback");
    } else {
      badge.textContent = "AI fallback · cần API key";
      badge.classList.add("fallback");
    }
  } catch {
    $("#ai-status").textContent = "Mất kết nối";
  }
}

function setDraft(task, result) {
  $("#task-title").value = task.title || "";
  $("#task-assignee").value = task.assignee || "";
  $("#task-course").value = task.course || "";
  $("#task-due").value = localInputValue(task.due_at);
  $("#task-importance").value = task.importance || "medium";
  $("#task-description").value = task.description || "";

  const banner = $("#draft-banner");
  const confidence = Number(task.confidence || 0);
  if (result.mode === "ai") {
    banner.className = "draft-banner ai";
    banner.textContent = `Gemini đã tạo bản nháp · độ tin cậy ${confidence}%. ${
      task.clarification_question || "Hãy kiểm tra lại trước khi lưu."
    }`;
  } else {
    banner.className = "draft-banner";
    banner.textContent = result.warning || "Đây là kết quả fallback, không phải output AI.";
  }
  $("#task-form").classList.remove("hidden");
  $("#task-title").focus();
}

async function parseQuickTask(event) {
  event.preventDefault();
  const button = $("#parse-button");
  const text = $("#quick-input").value.trim();
  if (!text) return;
  button.disabled = true;
  button.textContent = "Đang phân tích…";
  try {
    const result = await api("/api/ai/parse-task", {
      method: "POST",
      body: JSON.stringify({ text }),
    });
    setDraft(result.task, result);
    if (result.mode !== "ai") {
      showToast(result.warning, true);
    }
  } catch (error) {
    showToast(error.message, true);
  } finally {
    button.disabled = false;
    button.innerHTML = "<span>✨</span> AI đọc task";
  }
}

async function saveTask(event) {
  event.preventDefault();
  const dueValue = $("#task-due").value;
  const payload = {
    title: $("#task-title").value,
    assignee: $("#task-assignee").value,
    course: $("#task-course").value,
    due_at: dueValue ? new Date(dueValue).toISOString() : null,
    importance: $("#task-importance").value,
    description: $("#task-description").value,
    source: "quick capture",
  };
  try {
    await api("/api/tasks", { method: "POST", body: JSON.stringify(payload) });
    $("#task-form").classList.add("hidden");
    $("#quick-form").reset();
    showToast("Đã thêm task và tính lại thứ tự ưu tiên.");
    await loadDashboard();
  } catch (error) {
    showToast(error.message, true);
  }
}

function openCheckin(taskId) {
  const task = state.tasksById.get(String(taskId));
  if (!task) return;
  $("#checkin-id").value = task.id;
  $("#checkin-title").textContent = task.title;
  $("#checkin-progress").value = task.progress;
  $("#progress-value").textContent = `${task.progress}%`;
  $("#checkin-status").value = task.status;
  $("#checkin-note").value = task.blocked_reason || "";
  $("#checkin-dialog").showModal();
}

async function saveCheckin(event) {
  event.preventDefault();
  const taskId = $("#checkin-id").value;
  const status = $("#checkin-status").value;
  const note = $("#checkin-note").value;
  try {
    await api(`/api/tasks/${taskId}/check-in`, {
      method: "POST",
      body: JSON.stringify({
        progress: Number($("#checkin-progress").value),
        status,
        note,
        blocked_reason: status === "blocked" ? note : "",
      }),
    });
    $("#checkin-dialog").close();
    showToast("Đã cập nhật tiến độ và chạy lại rule engine.");
    await loadDashboard();
  } catch (error) {
    showToast(error.message, true);
  }
}

function renderToday() {
  const now = new Date();
  $("#today-weekday").textContent = new Intl.DateTimeFormat("vi-VN", {
    weekday: "long",
  }).format(now);
  $("#today-date").textContent = new Intl.DateTimeFormat("vi-VN", {
    day: "2-digit",
    month: "2-digit",
  }).format(now);
}

$("#quick-form").addEventListener("submit", parseQuickTask);
$("#task-form").addEventListener("submit", saveTask);
$("#cancel-draft").addEventListener("click", () => $("#task-form").classList.add("hidden"));
$("#refresh-button").addEventListener("click", loadDashboard);
$("#checkin-form").addEventListener("submit", saveCheckin);
$("#checkin-progress").addEventListener("input", (event) => {
  $("#progress-value").textContent = `${event.target.value}%`;
});
$("#close-checkin").addEventListener("click", () => $("#checkin-dialog").close());
$("#cancel-checkin").addEventListener("click", () => $("#checkin-dialog").close());

renderToday();
loadHealth();
loadDashboard();
