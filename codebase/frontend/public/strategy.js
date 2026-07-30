// AI Study Progress Assistant - Strategy Page Script
// Quản lý trạng thái chiến lược học tập, tương tác UI và đồng bộ localStorage

// Cấu trúc dữ liệu mặc định của chiến lược
const DEFAULT_STATE = {
  applied: false,
  tasks: {
    dailyStandup: {
      status: "not_started", // not_started, in_progress, done
      progress: 0
    },
    preflight: {
      status: "blocked", // blocked, in_progress, done
      progress: 30
    },
    day4: {
      status: "in_progress", // in_progress, done
      progress: 80
    }
  },
  blockerResolved: false,
  officeHourAdded: false,
  officeHourInterested: false
};

let state = { ...DEFAULT_STATE };

// Quản lý thông báo Toast
let toastTimeout = null;
function showToast(message, isSuccess = true) {
  const toast = document.getElementById("toast");
  const toastMsg = document.getElementById("toast-message");
  if (!toast || !toastMsg) return;

  toastMsg.textContent = message;
  toast.classList.remove("hidden");
  toast.classList.add("flex");

  clearTimeout(toastTimeout);
  toastTimeout = setTimeout(() => {
    toast.classList.remove("flex");
    toast.classList.add("hidden");
  }, 3000);
}

// Lưu trạng thái vào localStorage
function saveState() {
  localStorage.setItem("studyStrategyState", JSON.stringify(state));
  updateUI();
}

// Tải trạng thái từ localStorage
function loadState() {
  const saved = localStorage.getItem("studyStrategyState");
  if (saved) {
    try {
      state = JSON.parse(saved);
    } catch (e) {
      console.error("Lỗi khi parse studyStrategyState:", e);
      state = { ...DEFAULT_STATE };
    }
  } else {
    state = { ...DEFAULT_STATE };
  }
}

// Cập nhật giao diện dựa trên trạng thái (State) hiện tại
function updateUI() {
  // 1. Áp dụng kế hoạch tổng thể
  const btnApply = document.getElementById("btn-apply-plan");
  if (btnApply) {
    if (state.applied) {
      btnApply.textContent = "Đã áp dụng ✓";
      btnApply.className = "bg-emerald-600 hover:bg-emerald-700 text-white px-4 py-2 rounded-lg text-xs font-bold transition shadow-sm";
    } else {
      btnApply.textContent = "Áp dụng kế hoạch";
      btnApply.className = "bg-orange-500 hover:bg-orange-600 text-white px-4 py-2 rounded-lg text-xs font-bold transition shadow-sm";
    }
  }

  // 2. Cập nhật số liệu thống kê (Stats Block)
  const statBlocker = document.getElementById("stat-blocker");
  const statBlockerDesc = document.getElementById("stat-blocker-desc");
  if (statBlocker && statBlockerDesc) {
    if (state.blockerResolved) {
      statBlocker.textContent = "0";
      statBlocker.className = "text-3xl font-extrabold text-emerald-600 block mt-2";
      statBlockerDesc.textContent = "Đã giải quyết sạch";
      statBlockerDesc.className = "text-[10px] text-emerald-500 font-medium block mt-1";
    } else {
      statBlocker.textContent = "1";
      statBlocker.className = "text-3xl font-extrabold text-red-500 block mt-2";
      statBlockerDesc.textContent = "Đang chặn tiến trình";
      statBlockerDesc.className = "text-[10px] text-red-400 font-medium block mt-1";
    }
  }

  // 3. Task 1: Daily Stand-up UI
  const tStatusStandup = document.getElementById("task-status-standup");
  const tCardStandup = document.getElementById("task-card-standup");
  const btnStartStandup = document.getElementById("btn-start-standup");
  const btnDoneStandup = document.getElementById("btn-done-standup");

  if (tStatusStandup && tCardStandup) {
    if (state.tasks.dailyStandup.status === "done") {
      tStatusStandup.textContent = "Đã hoàn thành";
      tStatusStandup.className = "text-xs bg-emerald-50 text-emerald-600 border border-emerald-200 px-2.5 py-0.5 rounded-full font-bold";
      tCardStandup.classList.remove("border-l-rose-500");
      tCardStandup.classList.add("border-l-emerald-500");
      if (btnStartStandup) btnStartStandup.style.display = "none";
      if (btnDoneStandup) btnDoneStandup.style.display = "none";
    } else if (state.tasks.dailyStandup.status === "in_progress") {
      tStatusStandup.textContent = "Đang thực hiện";
      tStatusStandup.className = "text-xs bg-orange-50 text-orange-600 border border-orange-200 px-2.5 py-0.5 rounded-full font-bold";
      tCardStandup.classList.remove("border-l-rose-500");
      tCardStandup.classList.add("border-l-orange-500");
      if (btnStartStandup) btnStartStandup.textContent = "Tiếp tục làm";
    } else {
      tStatusStandup.textContent = "Chưa hoàn thành";
      tStatusStandup.className = "text-xs bg-slate-100 text-slate-600 border border-slate-200 px-2.5 py-0.5 rounded-full font-bold";
      tCardStandup.classList.remove("border-l-emerald-500", "border-l-orange-500");
      tCardStandup.classList.add("border-l-rose-500");
      if (btnStartStandup) btnStartStandup.style.display = "inline-block";
      if (btnDoneStandup) btnDoneStandup.style.display = "inline-block";
    }
  }

  // 4. Task 2: Preflight UI
  const tStatusPreflight = document.getElementById("task-status-preflight");
  const tCardPreflight = document.getElementById("task-card-preflight");
  const badgePreflight = document.getElementById("badge-preflight");
  const btnStartPreflight = document.getElementById("btn-start-preflight");
  const btnDonePreflight = document.getElementById("btn-done-preflight");
  const blockerDescTask2 = document.getElementById("blocker-desc-task2");

  if (tStatusPreflight && tCardPreflight) {
    if (state.blockerResolved || state.tasks.preflight.status === "done") {
      tStatusPreflight.textContent = "Đã xử lý xong";
      tStatusPreflight.className = "text-xs bg-emerald-50 text-emerald-600 border border-emerald-200 px-2.5 py-0.5 rounded-full font-bold";
      tCardPreflight.classList.remove("border-l-amber-500");
      tCardPreflight.classList.add("border-l-emerald-500");
      if (badgePreflight) {
        badgePreflight.textContent = "Đã gỡ blocker";
        badgePreflight.className = "text-[10px] bg-emerald-100 text-emerald-700 px-2 py-0.5 rounded font-bold uppercase";
      }
      if (blockerDescTask2) {
        blockerDescTask2.textContent = "Đã gỡ lỗi thành công ✓";
        blockerDescTask2.className = "text-emerald-600 font-semibold";
      }
      if (btnStartPreflight) btnStartPreflight.style.display = "none";
      if (btnDonePreflight) btnDonePreflight.style.display = "none";
    } else {
      tStatusPreflight.textContent = "Đang bị kẹt";
      tStatusPreflight.className = "text-xs bg-red-50 text-red-600 border border-red-200 px-2.5 py-0.5 rounded-full font-bold animate-pulse";
      tCardPreflight.classList.add("border-l-amber-500");
      if (badgePreflight) {
        badgePreflight.textContent = "Đang bị kẹt";
        badgePreflight.className = "text-[10px] bg-amber-100 text-amber-700 px-2 py-0.5 rounded font-bold uppercase";
      }
      if (blockerDescTask2) {
        blockerDescTask2.textContent = "Không chạy được preflight";
        blockerDescTask2.className = "text-red-600 font-bold";
      }
      if (btnStartPreflight) btnStartPreflight.style.display = "inline-block";
      if (btnDonePreflight) btnDonePreflight.style.display = "inline-block";
    }
  }

  // 5. Task 3: Day 4 UI
  const tStatusDay4 = document.getElementById("task-status-day4");
  const tCardDay4 = document.getElementById("task-card-day4");
  const progressBarDay4 = document.getElementById("progress-bar-day4");
  const progressTextDay4 = document.getElementById("progress-text-day4");
  const btnStartDay4 = document.getElementById("btn-start-day4");
  const btnDoneDay4 = document.getElementById("btn-done-day4");

  if (tStatusDay4 && tCardDay4 && progressBarDay4 && progressTextDay4) {
    progressBarDay4.style.width = `${state.tasks.day4.progress}%`;
    progressTextDay4.textContent = `${state.tasks.day4.progress}%`;

    if (state.tasks.day4.status === "done") {
      tStatusDay4.textContent = "Đã hoàn thành";
      tStatusDay4.className = "text-xs bg-emerald-50 text-emerald-600 border border-emerald-200 px-2.5 py-0.5 rounded-full font-bold";
      tCardDay4.classList.remove("border-l-blue-500");
      tCardDay4.classList.add("border-l-emerald-500");
      if (btnStartDay4) btnStartDay4.style.display = "none";
      if (btnDoneDay4) btnDoneDay4.style.display = "none";
    } else {
      tStatusDay4.textContent = "Đang thực hiện";
      tStatusDay4.className = "text-xs bg-orange-50 text-orange-600 border border-orange-200 px-2.5 py-0.5 rounded-full font-bold";
      tCardDay4.classList.add("border-l-blue-500");
      if (btnStartDay4) btnStartDay4.style.display = "inline-block";
      if (btnDoneDay4) btnDoneDay4.style.display = "inline-block";
    }
  }

  // 6. Blocker Card status
  const badgeBlockerStatus = document.getElementById("badge-blocker-status");
  const btnResolveBlocker = document.getElementById("btn-resolve-blocker");
  if (badgeBlockerStatus) {
    if (state.blockerResolved) {
      badgeBlockerStatus.textContent = "Đã xử lý";
      badgeBlockerStatus.className = "text-[10px] bg-emerald-100 text-emerald-700 border border-emerald-200 px-2 py-0.5 rounded font-bold uppercase";
      if (btnResolveBlocker) btnResolveBlocker.style.display = "none";
    } else {
      badgeBlockerStatus.textContent = "Đang bị kẹt";
      badgeBlockerStatus.className = "text-[10px] bg-red-50 text-red-600 border border-red-200 px-2 py-0.5 rounded font-bold uppercase animate-pulse";
      if (btnResolveBlocker) btnResolveBlocker.style.display = "inline-block";
    }
  }

  // 7. OH Event Card status
  const btnAddEvent = document.getElementById("btn-add-event");
  if (btnAddEvent) {
    if (state.officeHourAdded) {
      btnAddEvent.textContent = "Đã thêm vào kế hoạch ✓";
      btnAddEvent.className = "flex-1 bg-emerald-600 hover:bg-emerald-700 text-white py-1.5 rounded-lg text-xs font-bold transition shadow-sm";
    } else {
      btnAddEvent.textContent = "Thêm vào kế hoạch";
      btnAddEvent.className = "flex-1 bg-purple-600 hover:bg-purple-700 text-white py-1.5 rounded-lg text-xs font-bold transition shadow-sm";
    }
  }

  const btnStarEvent = document.getElementById("btn-star-event");
  if (btnStarEvent) {
    if (state.officeHourInterested) {
      btnStarEvent.textContent = "⭐ Đã quan tâm";
      btnStarEvent.className = "bg-purple-50 border border-purple-200 text-purple-700 hover:bg-purple-100 px-3 py-1.5 rounded-lg text-xs font-bold transition";
    } else {
      btnStarEvent.textContent = "⭐ Quan tâm";
      btnStarEvent.className = "bg-slate-50 border border-slate-200 text-slate-600 hover:bg-slate-100 px-3 py-1.5 rounded-lg text-xs font-bold transition";
    }
  }
}

// Thiết lập các sự kiện tương tác
function setupEventListeners() {
  // Áp dụng kế hoạch
  const btnApply = document.getElementById("btn-apply-plan");
  if (btnApply) {
    btnApply.addEventListener("click", () => {
      state.applied = true;
      showToast("Đã áp dụng kế hoạch chiến lược thành công!");
      saveState();
    });
  }

  // Điều chỉnh kế hoạch
  const btnAdjust = document.getElementById("btn-adjust-plan");
  if (btnAdjust) {
    btnAdjust.addEventListener("click", () => {
      showToast("Chức năng điều chỉnh kế hoạch đang được phát triển!", false);
    });
  }

  // Bỏ qua kế hoạch
  const btnSkip = document.getElementById("btn-skip-plan");
  if (btnSkip) {
    btnSkip.addEventListener("click", () => {
      state.applied = false;
      showToast("Đã bỏ qua kế hoạch học tập đề xuất.");
      saveState();
    });
  }

  // Task 1: Bắt đầu
  const btnStartStandup = document.getElementById("btn-start-standup");
  if (btnStartStandup) {
    btnStartStandup.addEventListener("click", () => {
      state.tasks.dailyStandup.status = "in_progress";
      showToast("Đã bắt đầu thực hiện: Nộp Daily Stand-up.");
      saveState();
    });
  }

  // Task 1: Hoàn thành
  const btnDoneStandup = document.getElementById("btn-done-standup");
  if (btnDoneStandup) {
    btnDoneStandup.addEventListener("click", () => {
      state.tasks.dailyStandup.status = "done";
      state.tasks.dailyStandup.progress = 100;
      showToast("Chúc mừng! Đã hoàn thành nộp Daily Stand-up.");
      saveState();
    });
  }

  // Task 2: Bắt đầu xử lý
  const btnStartPreflight = document.getElementById("btn-start-preflight");
  if (btnStartPreflight) {
    btnStartPreflight.addEventListener("click", () => {
      state.tasks.preflight.status = "in_progress";
      showToast("Đang tiến hành rà soát lỗi Preflight Provider...");
      saveState();
    });
  }

  // Task 2: Cập nhật tiến độ (Tăng thêm 10%)
  const btnProgressPreflight = document.getElementById("btn-progress-preflight");
  if (btnProgressPreflight) {
    btnProgressPreflight.addEventListener("click", () => {
      let prg = state.tasks.preflight.progress;
      if (prg < 90) {
        state.tasks.preflight.progress = prg + 10;
        showToast(`Tiến độ gỡ lỗi preflight đạt: ${state.tasks.preflight.progress}%`);
      } else {
        state.tasks.preflight.progress = 100;
        state.tasks.preflight.status = "done";
        state.blockerResolved = true;
        showToast("Lỗi preflight đã được xử lý xong hoàn toàn!");
      }
      saveState();
    });
  }

  // Task 2: Đã xử lý xong
  const btnDonePreflight = document.getElementById("btn-done-preflight");
  if (btnDonePreflight) {
    btnDonePreflight.addEventListener("click", () => {
      state.tasks.preflight.status = "done";
      state.tasks.preflight.progress = 100;
      state.blockerResolved = true;
      showToast("Đã gỡ blocker preflight thành công!");
      saveState();
    });
  }

  // Task 3: Tiếp tục
  const btnStartDay4 = document.getElementById("btn-start-day4");
  if (btnStartDay4) {
    btnStartDay4.addEventListener("click", () => {
      state.tasks.day4.status = "in_progress";
      showToast("Đang thực hiện viết code bài Day 4.");
      saveState();
    });
  }

  // Task 3: Cập nhật tiến độ
  const btnProgressDay4 = document.getElementById("btn-progress-day4");
  if (btnProgressDay4) {
    btnProgressDay4.addEventListener("click", () => {
      let prg = state.tasks.day4.progress;
      if (prg < 90) {
        state.tasks.day4.progress = prg + 10;
        showToast(`Tiến độ bài Day 4: ${state.tasks.day4.progress}%`);
      } else {
        state.tasks.day4.progress = 100;
        state.tasks.day4.status = "done";
        showToast("Tuyệt vời! Đã hoàn thành 100% bài thực hành Day 4.");
      }
      saveState();
    });
  }

  // Task 3: Đánh dấu hoàn thành
  const btnDoneDay4 = document.getElementById("btn-done-day4");
  if (btnDoneDay4) {
    btnDoneDay4.addEventListener("click", () => {
      state.tasks.day4.status = "done";
      state.tasks.day4.progress = 100;
      showToast("Đã hoàn tất toàn bộ bài Day 4 và sẵn sàng nộp bài!");
      saveState();
    });
  }

  // Blocker: Đánh dấu đã xử lý
  const btnResolveBlocker = document.getElementById("btn-resolve-blocker");
  if (btnResolveBlocker) {
    btnResolveBlocker.addEventListener("click", () => {
      state.blockerResolved = true;
      state.tasks.preflight.status = "done";
      state.tasks.preflight.progress = 100;
      showToast("Đã gỡ blocker: Đánh dấu lỗi preflight là đã giải quyết.");
      saveState();
    });
  }

  // Blocker: Sao chép hướng xử lý
  const btnCopySteps = document.getElementById("btn-copy-steps");
  if (btnCopySteps) {
    btnCopySteps.addEventListener("click", () => {
      const steps = [
        "1. Kiểm tra kỹ tệp cấu hình .env",
        "2. Kiểm tra provider đang sử dụng",
        "3. Kiểm tra tên model AI đăng ký",
        "4. Chạy lại lệnh kiểm tra preflight",
        "5. Lưu lại log lỗi chi tiết",
        "6. Đưa log lỗi đến Office Hour hoặc hỏi TA trực tiếp"
      ].join("\n");
      
      navigator.clipboard.writeText(steps)
        .then(() => showToast("Đã sao chép các bước xử lý vào Clipboard!"))
        .catch(err => console.error("Không thể sao chép:", err));
    });
  }

  // OH Event: Thêm vào kế hoạch
  const btnAddEvent = document.getElementById("btn-add-event");
  if (btnAddEvent) {
    btnAddEvent.addEventListener("click", () => {
      state.officeHourAdded = !state.officeHourAdded;
      if (state.officeHourAdded) {
        showToast("Đã thêm buổi Office Hour vào thời gian biểu hôm nay!");
      } else {
        showToast("Đã xóa Office Hour khỏi thời gian biểu.");
      }
      saveState();
    });
  }

  // OH Event: Quan tâm
  const btnStarEvent = document.getElementById("btn-star-event");
  if (btnStarEvent) {
    btnStarEvent.addEventListener("click", () => {
      state.officeHourInterested = !state.officeHourInterested;
      if (state.officeHourInterested) {
        showToast("Đã lưu sự kiện này vào danh sách quan tâm.");
      } else {
        showToast("Đã hủy quan tâm sự kiện.");
      }
      saveState();
    });
  }
}

// Section 14: Chuẩn bị tích hợp gọi API từ AI sau này
async function loadStrategyDetail() {
  try {
    // URL Mock / Thực tế của API
    const response = await fetch("/api/strategy", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        task_title: "Hoàn thành bài Day 4",
        importance: "high",
        status: "in_progress",
        blocker: "Lỗi preflight provider"
      })
    });
    if (response.ok) {
      const data = await response.json();
      console.log("Dữ liệu chiến lược tải thành công từ Backend API:", data);
      
      // Cập nhật gợi ý từ dữ liệu API AI nhận được
      const stratText = document.getElementById("strategy-recommendation-text");
      if (stratText && data.reason) {
        stratText.innerHTML = `<b>Đề xuất từ AI:</b> ${data.reason}<br><ul class="mt-2 pl-4 list-disc text-xs text-slate-500">${data.steps.map(s => `<li>${s}</li>`).join('')}</ul>`;
      }
    }
  } catch (error) {
    console.warn("Chưa khởi chạy API thật, sử dụng Mock data phía Frontend làm fallback.");
  }
}

// Khởi chạy
document.addEventListener("DOMContentLoaded", () => {
  loadState();
  updateUI();
  setupEventListeners();
  loadStrategyDetail(); // Gọi API chiến lược (chuẩn bị cho AI tích hợp)
});
