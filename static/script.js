/* =====================================================================
   AWS BILLING DASHBOARD PRO — JAVASCRIPT
   - Persistence Across Page Refreshes (Data, Theme, User Session)
   - Authentication Panel (Sign In, Create Account, Reset Password, Logout)
   - Interactive 3D Wireframe Canvas Background
   - Crontab Automation with Custom Timing & One-Time Runs
   - Custom Data Range & Dimension Selector with Live SMTP Email Dispatch
   - SMTP Mail Server Settings & Verification Testing
   ===================================================================== */

/* =====================================================================
   GLOBAL STATE & CONSTANTS
   ===================================================================== */
let _currentUser = null;
let _billingData = null;
let dailyVelocityChart = null;
let topServicesBarChart = null;
let _velocityPeriod = "14days";
let _activeTableTab = "services";

/* Multi-Color Palette from Screenshot */
const BAR_COLORS = [
    "#00c0f0", // Amazon Elastic Compute (Cyan)
    "#7c83fd", // EC2 - Other (Periwinkle Blue)
    "#b085f5", // Amazon OpenSearch (Lavender Purple)
    "#f472b6", // Savings Plans (Pink)
    "#fb923c", // Amazon Simple Storage S3 (Orange)
    "#34d399", // Amazon Virtual Private Cloud (Mint Green)
    "#38bdf8", // DynamoDB
    "#a78bfa", // CloudFront
    "#f43f5e", // Route 53
    "#fbbf24"  // CloudWatch
];

/* Default Initial Data (Matches Screenshot Values) */
const DEFAULT_SAMPLE_DATA = {
    current_cost: 268.42,
    previous_cost: 930.59,
    forecast: 268.42,
    tax: 18.50,
    period: {
        start: "2026-09-01",
        end: "2026-09-10"
    },
    daily: {
        dates: [
            "2026-08-28", "2026-08-29", "2026-08-30", "2026-08-31",
            "2026-09-01", "2026-09-02", "2026-09-03", "2026-09-04",
            "2026-09-05", "2026-09-06", "2026-09-07", "2026-09-08",
            "2026-09-09", "2026-09-10"
        ],
        costs: [28.5, 29.8, 29.4, 29.2, 28.1, 26.5, 27.2, 29.0, 30.2, 30.0, 29.8, 28.5, 27.9, 8.2]
    },
    services: [
        { service: "Amazon Elastic Compute Cloud (EC2)", cost: 142.20, runs: 13, status: "Healthy" },
        { service: "EC2 - Other", cost: 135.50, runs: 24, status: "Healthy" },
        { service: "Amazon OpenSearch Service", cost: 68.40, runs: 6, status: "Healthy" },
        { service: "Savings Plans for Compute", cost: 42.10, runs: 2, status: "Healthy" },
        { service: "Amazon Simple Storage Service (S3)", cost: 28.30, runs: 11, status: "Healthy" },
        { service: "Amazon Virtual Private Cloud (VPC)", cost: 18.20, runs: 8, status: "Healthy" },
        { service: "Amazon DynamoDB", cost: 12.40, runs: 14, status: "Healthy" },
        { service: "AWS Lambda", cost: 9.00, runs: 32, status: "Healthy" },
        { service: "Amazon CloudFront", cost: 6.80, runs: 4, status: "Healthy" },
        { service: "Amazon Route 53", cost: 3.50, runs: 1, status: "Healthy" },
        { service: "Amazon CloudWatch", cost: 2.10, runs: 5, status: "Healthy" },
        { service: "AWS Cost Explorer API", cost: 0.40, runs: 2, status: "Healthy" }
    ],
    regions: [
        { region: "us-east-1 (N. Virginia)", cost: 168.20, share: 62.7 },
        { region: "us-west-2 (Oregon)", cost: 58.40, share: 21.8 },
        { region: "eu-west-1 (Ireland)", cost: 26.10, share: 9.7 },
        { region: "ap-south-1 (Mumbai)", cost: 11.20, share: 4.2 },
        { region: "Global / Edge", cost: 4.52, share: 1.6 }
    ]
};

/* =====================================================================
   INITIALIZATION & PERSISTENCE RESTORATION
   ===================================================================== */
document.addEventListener("DOMContentLoaded", function () {
    // 1. Restore Theme from localStorage
    const savedTheme = localStorage.getItem("aws_theme_mode") || "dark";
    document.documentElement.setAttribute("data-theme", savedTheme);
    const themeLabel = document.getElementById("themeLabelText");
    if (themeLabel) themeLabel.textContent = savedTheme === "dark" ? "12 Colors (Dark)" : "12 Colors (Light)";

    // 2. Start 3D background canvas
    init3DBackgroundMesh();

    // 3. Restore User Session
    const savedUserStr = localStorage.getItem("aws_billing_user");
    if (savedUserStr) {
        try {
            _currentUser = JSON.parse(savedUserStr);
            applyUserSession(_currentUser);
            hideAuthOverlay();
        } catch (e) {
            showAuthOverlay();
        }
    } else {
        showAuthOverlay();
    }

    // 4. Restore Billing Data from localStorage (Never erased on refresh!)
    const savedDataStr = localStorage.getItem("aws_billing_data");
    if (savedDataStr) {
        try {
            _billingData = JSON.parse(savedDataStr);
        } catch (e) {
            _billingData = DEFAULT_SAMPLE_DATA;
        }
    } else {
        _billingData = DEFAULT_SAMPLE_DATA;
        localStorage.setItem("aws_billing_data", JSON.stringify(_billingData));
    }

    // 5. Render Full Dashboard
    renderFullDashboard(_billingData);

    // 6. Pre-fill custom services and load settings
    populateCustomServicesChecklist(_billingData.services);
    fetchCronJobsList();
    loadSmtpSettings();
});

/* =====================================================================
   AUTHENTICATION LOGIC (SIGN IN, SIGN UP, FORGOT, LOGOUT)
   ===================================================================== */
function showAuthOverlay() {
    const overlay = document.getElementById("authOverlay");
    if (overlay) overlay.classList.add("show");
}

function hideAuthOverlay() {
    const overlay = document.getElementById("authOverlay");
    if (overlay) overlay.classList.remove("show");
}

function switchAuthTab(tab) {
    const btnSignIn = document.getElementById("authTabSignInBtn");
    const btnSignUp = document.getElementById("authTabSignUpBtn");
    const btnForgot = document.getElementById("authTabForgotBtn");
    const formSignIn = document.getElementById("signInForm");
    const formSignUp = document.getElementById("signUpForm");
    const formForgot = document.getElementById("forgotForm");

    btnSignIn.classList.remove("active");
    btnSignUp.classList.remove("active");
    btnForgot.classList.remove("active");
    formSignIn.style.display = "none";
    formSignUp.style.display = "none";
    formForgot.style.display = "none";

    if (tab === "signin") {
        btnSignIn.classList.add("active");
        formSignIn.style.display = "block";
    } else if (tab === "signup") {
        btnSignUp.classList.add("active");
        formSignUp.style.display = "block";
    } else {
        btnForgot.classList.add("active");
        formForgot.style.display = "block";
    }
}

async function handleSignIn(e) {
    e.preventDefault();
    const email = document.getElementById("loginEmail").value.trim();
    const password = document.getElementById("loginPassword").value.trim();
    const rememberMe = document.getElementById("rememberMe").checked;
    const statusBox = document.getElementById("signInStatus");

    statusBox.textContent = "Verifying credentials...";
    statusBox.style.color = "var(--cyan-accent)";

    try {
        const res = await fetch("/api/auth/login", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ email: email, password: password })
        });
        const json = await res.json();

        if (json.success) {
            _currentUser = json.user;
            if (rememberMe) {
                localStorage.setItem("aws_billing_user", JSON.stringify(_currentUser));
            }
            applyUserSession(_currentUser);
            hideAuthOverlay();
            statusBox.textContent = "";
        } else {
            statusBox.textContent = "Error: " + (json.error || "Authentication failed");
            statusBox.style.color = "var(--rose)";
        }
    } catch (err) {
        statusBox.textContent = "Connection error: " + err.message;
        statusBox.style.color = "var(--rose)";
    }
}

async function handleSignUp(e) {
    e.preventDefault();
    const name = document.getElementById("regName").value.trim();
    const email = document.getElementById("regEmail").value.trim();
    const password = document.getElementById("regPassword").value.trim();
    const statusBox = document.getElementById("signUpStatus");

    statusBox.textContent = "Creating account...";
    statusBox.style.color = "var(--cyan-accent)";

    try {
        const res = await fetch("/api/auth/register", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ name: name, email: email, password: password })
        });
        const json = await res.json();

        if (json.success) {
            _currentUser = json.user;
            localStorage.setItem("aws_billing_user", JSON.stringify(_currentUser));
            applyUserSession(_currentUser);
            hideAuthOverlay();
            statusBox.textContent = "";
        } else {
            statusBox.textContent = "Error: " + (json.error || "Failed to create account");
            statusBox.style.color = "var(--rose)";
        }
    } catch (err) {
        statusBox.textContent = "Error: " + err.message;
        statusBox.style.color = "var(--rose)";
    }
}

async function handleForgotPassword(e) {
    e.preventDefault();
    const email = document.getElementById("forgotEmail").value.trim();
    const newPassword = document.getElementById("forgotNewPassword").value.trim();
    const statusBox = document.getElementById("forgotStatus");

    statusBox.textContent = "Processing reset...";
    statusBox.style.color = "var(--cyan-accent)";

    try {
        const res = await fetch("/api/auth/forgot-password", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ email: email, new_password: newPassword })
        });
        const json = await res.json();

        if (json.success) {
            statusBox.textContent = "✓ " + json.message;
            statusBox.style.color = "var(--emerald)";
            setTimeout(() => switchAuthTab("signin"), 1500);
        } else {
            statusBox.textContent = "Error: " + (json.error || "Password reset failed");
            statusBox.style.color = "var(--rose)";
        }
    } catch (err) {
        statusBox.textContent = "Error: " + err.message;
        statusBox.style.color = "var(--rose)";
    }
}

function handleLogout() {
    if (!confirm("Are you sure you want to log out of your dashboard?")) return;
    localStorage.removeItem("aws_billing_user");
    _currentUser = null;
    closeSettingsModal();
    showAuthOverlay();
    switchAuthTab("signin");
}

function applyUserSession(user) {
    if (!user) return;
    const email = user.email || "jigal.prajapati@bytestechnolab.com";
    const name = user.name || "Jigal Prajapati";
    const role = user.role || "Super Administrator";
    const initials = name.split(" ").map(n => n[0]).join("").toUpperCase().slice(0, 2) || "JP";

    // Header email display
    const headerEmail = document.getElementById("connectedEmailDisplay");
    if (headerEmail) headerEmail.textContent = email;

    // Sidebar user profile
    const sideName = document.getElementById("displayAccountSidebar");
    if (sideName) sideName.textContent = name;
    const sideAvatar = document.getElementById("userAvatar");
    if (sideAvatar) sideAvatar.textContent = initials;
    const roleBadge = document.getElementById("userRoleBadge");
    if (roleBadge) roleBadge.textContent = role;

    // Account settings modal tab
    const profName = document.getElementById("profileNameDisplay");
    if (profName) profName.textContent = name;
    const profEmail = document.getElementById("profileEmailDisplay");
    if (profEmail) profEmail.textContent = email;
    const profRole = document.getElementById("profileRoleDisplay");
    if (profRole) profRole.textContent = role;
    const profAvatar = document.getElementById("profileAvatarLarge");
    if (profAvatar) profAvatar.textContent = initials;
}

async function handleChangePassword(e) {
    e.preventDefault();
    const newPwd = document.getElementById("newAccountPassword").value.trim();
    const confirmPwd = document.getElementById("confirmAccountPassword").value.trim();
    const statusBox = document.getElementById("changePasswordStatus");

    if (newPwd !== confirmPwd) {
        statusBox.textContent = "Passwords do not match.";
        statusBox.style.color = "var(--rose)";
        return;
    }

    const email = _currentUser ? _currentUser.email : "jigal.prajapati@bytestechnolab.com";
    statusBox.textContent = "Updating password...";
    statusBox.style.color = "var(--cyan-accent)";

    try {
        const res = await fetch("/api/auth/forgot-password", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ email: email, new_password: newPwd })
        });
        const json = await res.json();
        if (json.success) {
            statusBox.textContent = "✓ Password successfully updated!";
            statusBox.style.color = "var(--emerald)";
            document.getElementById("newAccountPassword").value = "";
            document.getElementById("confirmAccountPassword").value = "";
        } else {
            statusBox.textContent = "Error: " + json.error;
            statusBox.style.color = "var(--rose)";
        }
    } catch (err) {
        statusBox.textContent = "Error: " + err.message;
        statusBox.style.color = "var(--rose)";
    }
}

/* =====================================================================
   SETTINGS & ACCOUNT MODAL (TAB CONTROL)
   ===================================================================== */
function openSettingsModal() {
    const modal = document.getElementById("settingsModal");
    if (modal) {
        modal.classList.add("open");
        document.body.style.overflow = "hidden";
        if (_currentUser) applyUserSession(_currentUser);
        fetchCronJobsList();
        loadSmtpSettings();
    }
}

function closeSettingsModal() {
    const modal = document.getElementById("settingsModal");
    if (modal) {
        modal.classList.remove("open");
        document.body.style.overflow = "";
    }
}

function switchSettingsTab(tab) {
    const tabs = ["Account", "Cron", "Custom", "Smtp"];
    tabs.forEach(t => {
        const btn = document.getElementById(`tabBtn${t}`);
        const content = document.getElementById(`settings${t}Content`);
        if (btn) btn.classList.remove("active");
        if (content) content.style.display = "none";
    });

    if (tab === "account") {
        document.getElementById("tabBtnAccount").classList.add("active");
        document.getElementById("settingsAccountContent").style.display = "block";
    } else if (tab === "cron") {
        document.getElementById("tabBtnCron").classList.add("active");
        document.getElementById("settingsCronContent").style.display = "block";
    } else if (tab === "custom-reports") {
        document.getElementById("tabBtnCustom").classList.add("active");
        document.getElementById("settingsCustomContent").style.display = "block";
    } else if (tab === "smtp") {
        document.getElementById("tabBtnSmtp").classList.add("active");
        document.getElementById("settingsSmtpContent").style.display = "block";
    }
}

function openSettingsTab(tab) {
    openSettingsModal();
    switchSettingsTab(tab);
}

/* =====================================================================
   INTERACTIVE 3D WIREFRAME MESH BACKGROUND
   ===================================================================== */
function init3DBackgroundMesh() {
    const canvas = document.getElementById("bg3dCanvas");
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    let width, height;

    function resize() {
        width = canvas.width = window.innerWidth;
        height = canvas.height = window.innerHeight;
    }
    resize();
    window.addEventListener("resize", resize);

    const nodes = [];
    const phi = (1 + Math.sqrt(5)) / 2;
    const baseVertices = [
        [-1,  phi, 0], [ 1,  phi, 0], [-1, -phi, 0], [ 1, -phi, 0],
        [ 0, -1,  phi], [ 0,  1,  phi], [ 0, -1, -phi], [ 0,  1, -phi],
        [ phi, 0, -1], [ phi, 0,  1], [-phi, 0, -1], [-phi, 0,  1]
    ];

    const radius = 280;
    baseVertices.forEach(v => {
        const len = Math.sqrt(v[0]*v[0] + v[1]*v[1] + v[2]*v[2]);
        nodes.push({
            x: (v[0] / len) * radius,
            y: (v[1] / len) * radius,
            z: (v[2] / len) * radius
        });
    });

    const edges = [];
    for (let i = 0; i < nodes.length; i++) {
        for (let j = i + 1; j < nodes.length; j++) {
            const dx = nodes[i].x - nodes[j].x;
            const dy = nodes[i].y - nodes[j].y;
            const dz = nodes[i].z - nodes[j].z;
            const dist = Math.sqrt(dx*dx + dy*dy + dz*dz);
            if (dist < radius * 1.2) edges.push([i, j]);
        }
    }

    let rotX = 0.2, rotY = 0.3;

    function render() {
        ctx.clearRect(0, 0, width, height);
        rotX += 0.0016;
        rotY += 0.0022;

        const centerX = width * 0.72;
        const centerY = height * 0.48;
        const cosX = Math.cos(rotX), sinX = Math.sin(rotX);
        const cosY = Math.cos(rotY), sinY = Math.sin(rotY);

        const projected = nodes.map(n => {
            const x1 = n.x * cosY - n.z * sinY;
            const z1 = n.z * cosY + n.x * sinY;
            const y2 = n.y * cosX - z1 * sinX;
            const z2 = z1 * cosX + n.y * sinX;
            const scale = 500 / (500 + z2);
            return { x: centerX + x1 * scale, y: centerY + y2 * scale, scale: scale };
        });

        ctx.lineWidth = 1.1;
        ctx.strokeStyle = "rgba(0, 192, 240, 0.16)";
        edges.forEach(([i, j]) => {
            ctx.beginPath();
            ctx.moveTo(projected[i].x, projected[i].y);
            ctx.lineTo(projected[j].x, projected[j].y);
            ctx.stroke();
        });

        projected.forEach(p => {
            ctx.beginPath();
            ctx.arc(p.x, p.y, 2.2 * p.scale, 0, Math.PI * 2);
            ctx.fillStyle = "rgba(0, 192, 240, 0.45)";
            ctx.fill();
        });

        requestAnimationFrame(render);
    }
    render();
}

/* =====================================================================
   DASHBOARD METRICS & CHARTS RENDERING
   ===================================================================== */
function renderFullDashboard(data) {
    if (!data) return;

    const current = Number(data.current_cost || 0);
    const previous = Number(data.previous_cost || 0);
    const forecast = Number(data.forecast || 0);

    const kpiCurrent = document.getElementById("kpiCurrentCost");
    if (kpiCurrent) kpiCurrent.textContent = formatCurrency(current);

    const kpiPrevious = document.getElementById("kpiPreviousCost");
    if (kpiPrevious) kpiPrevious.textContent = formatCurrency(previous);

    const kpiForecast = document.getElementById("kpiForecastCost");
    if (kpiForecast) kpiForecast.textContent = formatCurrency(forecast);

    const kpiActive = document.getElementById("kpiActiveServicesVal");
    if (kpiActive) kpiActive.textContent = "$9.00";

    const changeTag = document.getElementById("kpiChangeTag");
    if (changeTag && previous > 0) {
        const diffPct = (((current - previous) / previous) * 100).toFixed(2);
        changeTag.textContent = `${diffPct}% vs last month`;
    }

    renderDailyVelocityChart(data.daily || {});
    renderTopServicesBarChart(data.services || []);
    renderServicesTable(data.services || []);
    renderRegionsTable(data.regions || []);
}

function renderDailyVelocityChart(daily) {
    const canvas = document.getElementById("dailyVelocityChart");
    if (!canvas) return;

    if (dailyVelocityChart) {
        dailyVelocityChart.destroy();
        dailyVelocityChart = null;
    }

    const ctx = canvas.getContext("2d");
    const dates = daily.dates || [];
    const costs = daily.costs || [];

    const gradient = ctx.createLinearGradient(0, 0, 0, canvas.height || 260);
    gradient.addColorStop(0, "rgba(0, 192, 240, 0.28)");
    gradient.addColorStop(0.75, "rgba(0, 192, 240, 0.05)");
    gradient.addColorStop(1, "rgba(0, 192, 240, 0)");

    dailyVelocityChart = new Chart(canvas, {
        type: "line",
        data: {
            labels: dates.map(d => formatDateShort(d)),
            datasets: [{
                label: "Daily Spend Velocity",
                data: costs.map(Number),
                borderColor: "#00c0f0",
                borderWidth: 2.8,
                backgroundColor: gradient,
                fill: true,
                tension: 0.38,
                pointRadius: 0,
                pointHoverRadius: 6,
                pointHoverBackgroundColor: "#00c0f0",
                pointHoverBorderColor: "#ffffff",
                pointHoverBorderWidth: 2
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            interaction: { intersect: false, mode: "index" },
            plugins: {
                legend: { display: false },
                tooltip: {
                    backgroundColor: "#111a2e",
                    titleColor: "#f4f4f5",
                    bodyColor: "#00c0f0",
                    borderColor: "rgba(0, 192, 240, 0.3)",
                    borderWidth: 1,
                    callbacks: {
                        label: function (ctx) { return " Velocity: " + formatCurrency(ctx.raw); }
                    }
                }
            },
            scales: {
                x: {
                    grid: { display: false },
                    ticks: { color: "#64748b", font: { size: 10 } }
                },
                y: {
                    beginAtZero: true,
                    max: 36,
                    grid: { color: "rgba(255, 255, 255, 0.05)" },
                    ticks: {
                        color: "#64748b",
                        font: { size: 10 },
                        stepSize: 8,
                        callback: function (val) { return "$" + val; }
                    }
                }
            }
        }
    });
}

function toggleVelocityPeriod() {
    const pill = document.getElementById("velocityPeriodPill");
    if (_velocityPeriod === "14days") {
        _velocityPeriod = "30days";
        pill.textContent = "Last 30 Days";
    } else {
        _velocityPeriod = "14days";
        pill.textContent = "Last 14 Days";
    }
    if (_billingData) renderDailyVelocityChart(_billingData.daily || {});
}

function renderTopServicesBarChart(services) {
    const canvas = document.getElementById("topServicesBarChart");
    if (!canvas) return;

    if (topServicesBarChart) {
        topServicesBarChart.destroy();
        topServicesBarChart = null;
    }

    const top = services.slice(0, 6);
    const labels = top.map(s => shortenText(s.service, 22));
    const values = top.map(s => Number(s.cost || 0));

    topServicesBarChart = new Chart(canvas, {
        type: "bar",
        data: {
            labels: labels,
            datasets: [{
                data: values,
                backgroundColor: BAR_COLORS.slice(0, top.length),
                borderRadius: 8,
                borderSkipped: false,
                barThickness: 16
            }]
        },
        options: {
            indexAxis: "y",
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: { display: false },
                tooltip: {
                    backgroundColor: "#111a2e",
                    titleColor: "#f4f4f5",
                    borderColor: "rgba(255, 255, 255, 0.1)",
                    borderWidth: 1,
                    callbacks: {
                        label: function (ctx) { return " Cost: " + formatCurrency(ctx.raw); }
                    }
                }
            },
            scales: {
                x: { display: false, grid: { display: false } },
                y: { grid: { display: false }, ticks: { color: "#94a3b8", font: { size: 10, weight: "500" } } }
            }
        }
    });
}

/* =====================================================================
   DATA TABLES (SERVICES & REGIONS)
   ===================================================================== */
function switchTableTab(tab) {
    _activeTableTab = tab;
    const btnSvc = document.getElementById("tabBtnServices");
    const btnReg = document.getElementById("tabBtnRegions");
    const wrapSvc = document.getElementById("servicesTableWrap");
    const wrapReg = document.getElementById("regionsTableWrap");

    if (tab === "services") {
        btnSvc.classList.add("active");
        btnReg.classList.remove("active");
        wrapSvc.style.display = "block";
        wrapReg.style.display = "none";
    } else {
        btnReg.classList.add("active");
        btnSvc.classList.remove("active");
        wrapReg.style.display = "block";
        wrapSvc.style.display = "none";
    }
}

function filterActiveTable(query) {
    if (_activeTableTab === "services") {
        renderServicesTable(_billingData ? _billingData.services : [], query);
    } else {
        renderRegionsTable(_billingData ? _billingData.regions : [], query);
    }
}

function renderServicesTable(services, query = "") {
    const tbody = document.getElementById("servicesTable");
    if (!tbody) return;

    let items = (services || []).slice();
    if (query.trim()) {
        const q = query.toLowerCase().trim();
        items = items.filter(s => s.service.toLowerCase().includes(q));
    }

    const totalCost = (_billingData && _billingData.current_cost) ? _billingData.current_cost : 1;
    const maxCost = items.length > 0 ? Number(items[0].cost || 1) : 1;

    tbody.innerHTML = items.map((item, i) => {
        const cost = Number(item.cost || 0);
        const share = ((cost / totalCost) * 100).toFixed(1);
        const barW = Math.min(100, Math.round((cost / maxCost) * 100));

        return `
            <tr>
                <td style="color: var(--text-3); font-weight: 700;">${i + 1}</td>
                <td style="font-weight: 600; color: var(--text-1);">${escapeHtml(item.service)}</td>
                <td style="font-weight: 700; color: var(--text-1);">${formatCurrency(cost)}</td>
                <td style="color: var(--text-3);">${share}%</td>
                <td>
                    <div class="table-bar-outer">
                        <div class="table-bar-inner" style="width: ${barW}%;"></div>
                    </div>
                </td>
                <td><span class="status-pill healthy">Active</span></td>
            </tr>
        `;
    }).join("");
}

function renderRegionsTable(regions, query = "") {
    const tbody = document.getElementById("regionsTable");
    if (!tbody) return;

    let items = (regions || []).slice();
    if (query.trim()) {
        const q = query.toLowerCase().trim();
        items = items.filter(r => r.region.toLowerCase().includes(q));
    }

    const totalCost = (_billingData && _billingData.current_cost) ? _billingData.current_cost : 1;
    const maxCost = items.length > 0 ? Number(items[0].cost || 1) : 1;

    tbody.innerHTML = items.map((item, i) => {
        const cost = Number(item.cost || 0);
        const share = item.share || ((cost / totalCost) * 100).toFixed(1);
        const barW = Math.min(100, Math.round((cost / maxCost) * 100));

        return `
            <tr>
                <td style="color: var(--text-3); font-weight: 700;">${i + 1}</td>
                <td style="font-weight: 600; color: var(--text-1);">${escapeHtml(item.region)}</td>
                <td style="font-weight: 700; color: var(--text-1);">${formatCurrency(cost)}</td>
                <td style="color: var(--text-3);">${share}%</td>
                <td>
                    <div class="table-bar-outer">
                        <div class="table-bar-inner" style="width: ${barW}%; background: var(--periwinkle);"></div>
                    </div>
                </td>
                <td><span style="font-weight:700; font-size:11px; color:var(--cyan-accent);">Active</span></td>
            </tr>
        `;
    }).join("");
}

function sortTable(type, col) {
    if (type === "services") {
        _serviceSort.dir = (_serviceSort.col === col && _serviceSort.dir === "desc") ? "asc" : "desc";
        _serviceSort.col = col;
        renderServicesTable(_billingData ? _billingData.services : []);
    } else {
        _regionSort.dir = (_regionSort.col === col && _regionSort.dir === "desc") ? "asc" : "desc";
        _regionSort.col = col;
        renderRegionsTable(_billingData ? _billingData.regions : []);
    }
}

/* =====================================================================
   CONNECT AWS API & DATA PERSISTENCE
   ===================================================================== */
async function fetchBilling() {
    const accessKey = document.getElementById("accessKey").value.trim();
    const secretKey = document.getElementById("secretKey").value.trim();
    const region = document.getElementById("region").value;
    const accountName = document.getElementById("accountName").value.trim() || (_currentUser ? _currentUser.email : "AWS Production");

    const statusEl = document.getElementById("status");
    const button = document.getElementById("fetchButton");
    const buttonText = document.getElementById("buttonText");

    if (!accessKey || !secretKey) {
        statusEl.textContent = "Please enter AWS Access Key ID and Secret Access Key.";
        statusEl.style.color = "var(--rose)";
        return;
    }

    button.disabled = true;
    buttonText.textContent = "Connecting AWS...";
    statusEl.textContent = "Querying live AWS Cost Explorer API...";

    try {
        const response = await fetch("/api/billing", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                access_key: accessKey,
                secret_key: secretKey,
                region: region
            })
        });

        const result = await response.json();
        if (!result.success) throw new Error(result.error || "Unable to retrieve billing data.");

        _billingData = result.data;
        // PERSIST IN LOCALSTORAGE SO REFRESH NEVER ERASES IT!
        localStorage.setItem("aws_billing_data", JSON.stringify(_billingData));

        const emailDisplay = document.getElementById("connectedEmailDisplay");
        if (emailDisplay) emailDisplay.textContent = accountName;

        renderFullDashboard(_billingData);
        populateCustomServicesChecklist(_billingData.services);

        statusEl.textContent = "✓ Connected & refreshed live AWS Cost Explorer metrics.";
        statusEl.style.color = "#34d399";

        setTimeout(() => {
            const panel = document.getElementById("connectPanel");
            if (panel) panel.classList.remove("open");
        }, 1500);

    } catch (err) {
        console.error("fetchBilling error:", err);
        statusEl.textContent = "Error: " + err.message;
        statusEl.style.color = "var(--rose)";
    } finally {
        button.disabled = false;
        buttonText.textContent = "Fetch Live Billing Data";
    }
}

function toggleConnectPanel() {
    const p = document.getElementById("connectPanel");
    if (p) {
        p.classList.toggle("open");
        if (p.classList.contains("open")) p.scrollIntoView({ behavior: "smooth" });
    }
}

function onRefresh() {
    fetchBilling();
}

function toggleSidebar() {
    const sb = document.getElementById("sidebar");
    if (sb) sb.classList.toggle("open");
}

function navActivate(el) {
    document.querySelectorAll(".nav-item").forEach(n => n.classList.remove("active"));
    el.classList.add("active");
}

function toggleThemePalette() {
    const root = document.documentElement;
    const current = root.getAttribute("data-theme");
    const next = current === "dark" ? "light" : "dark";
    root.setAttribute("data-theme", next);
    // PERSIST THEME ACROSS REFRESH
    localStorage.setItem("aws_theme_mode", next);

    const themeLabel = document.getElementById("themeLabelText");
    if (themeLabel) themeLabel.textContent = next === "dark" ? "12 Colors (Dark)" : "12 Colors (Light)";

    if (_billingData) {
        renderDailyVelocityChart(_billingData.daily || {});
        renderTopServicesBarChart(_billingData.services || []);
    }
}

function filterByServiceName(name) {
    const input = document.getElementById("tableFilterInput");
    if (input) {
        input.value = name;
        switchTableTab("services");
        filterActiveTable(name);
        document.getElementById("servicesTableWrap").scrollIntoView({ behavior: "smooth" });
    }
}

function toggleSecretKey() {
    const input = document.getElementById("secretKey");
    if (input.type === "password") input.type = "text";
    else input.type = "password";
}

/* =====================================================================
   CRONTAB AUTOMATION WITH CUSTOM TIMING (GUI)
   ===================================================================== */
function toggleAddCronForm() {
    const f = document.getElementById("addCronForm");
    if (f) f.style.display = f.style.display === "none" ? "block" : "none";
}

function onCronScheduleChange(val) {
    const timeWrap = document.getElementById("cronTimeWrap");
    const oneTimeWrap = document.getElementById("cronOneTimeDateWrap");
    const customExprWrap = document.getElementById("cronCustomExprWrap");

    if (val === "one_time") {
        timeWrap.style.display = "block";
        oneTimeWrap.style.display = "block";
        customExprWrap.style.display = "none";
    } else if (val === "custom") {
        timeWrap.style.display = "block";
        oneTimeWrap.style.display = "none";
        customExprWrap.style.display = "block";
    } else {
        timeWrap.style.display = "block";
        oneTimeWrap.style.display = "none";
        customExprWrap.style.display = "none";
    }
}

async function fetchCronJobsList() {
    const tbody = document.getElementById("cronJobsTableBody");
    if (!tbody) return;

    try {
        const res = await fetch("/api/admin/cron");
        const json = await res.json();
        const jobs = json.jobs || [];

        if (jobs.length === 0) {
            tbody.innerHTML = '<tr><td colspan="7" style="text-align:center; padding:20px; color:var(--text-3);">No automated crontabs configured yet.</td></tr>';
            return;
        }

        tbody.innerHTML = jobs.map(job => {
            const activeBadge = job.active
                ? '<span class="cron-badge active-cron">Active</span>'
                : '<span class="cron-badge paused-cron">Paused</span>';

            const toggleLabel = job.active ? "Pause" : "Resume";

            return `
                <tr>
                    <td style="font-weight:700; color:var(--text-1);">${escapeHtml(job.name)}</td>
                    <td style="color:var(--cyan-accent); font-weight:500;">${escapeHtml(job.email)}</td>
                    <td style="color:var(--text-2); font-size:11.5px;">${escapeHtml(job.time || job.schedule)}</td>
                    <td style="color:var(--text-3); text-transform:capitalize;">${job.format.toUpperCase()}</td>
                    <td>${activeBadge}</td>
                    <td style="color:var(--text-3); font-size:11px;">${job.last_run || "Never"}</td>
                    <td style="text-align:right;">
                        <button class="action-btn-sm action-btn-run" onclick="runCronNow('${job.id}')" title="Trigger immediate report test">⚡ Run Now</button>
                        <button class="action-btn-sm" onclick="toggleCronJob('${job.id}')">${toggleLabel}</button>
                        <button class="action-btn-sm action-btn-del" onclick="deleteCronJob('${job.id}')">✕</button>
                    </td>
                </tr>
            `;
        }).join("");

    } catch (e) {
        console.error("fetchCronJobsList error:", e);
    }
}

async function saveNewCronJob() {
    const name = document.getElementById("newCronName").value.trim();
    const email = document.getElementById("newCronEmail").value.trim();
    const schedule = document.getElementById("newCronSchedule").value;
    const customTime = document.getElementById("newCronTime").value;
    const oneTimeDate = document.getElementById("newCronOneTimeDate").value;
    const customExpr = document.getElementById("newCronCustomExpr").value.trim();
    const format = document.getElementById("newCronFormat").value;

    if (!email) {
        alert("Please enter a recipient email address.");
        return;
    }

    try {
        const res = await fetch("/api/admin/cron", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                name: name || "Custom AWS Cost Report",
                email: email,
                schedule: schedule,
                time: customTime,
                is_one_time: schedule === "one_time",
                one_time_date: oneTimeDate,
                cron_expr: customExpr,
                format: format
            })
        });

        const json = await res.json();
        if (json.success) {
            alert(json.message);
            document.getElementById("newCronEmail").value = "";
            toggleAddCronForm();
            fetchCronJobsList();
        } else {
            alert("Error: " + json.error);
        }
    } catch (e) {
        alert("Failed to save cron job: " + e.message);
    }
}

async function toggleCronJob(id) {
    try {
        const res = await fetch(`/api/admin/cron/toggle/${id}`, { method: "POST" });
        const json = await res.json();
        if (json.success) fetchCronJobsList();
    } catch (e) {
        console.error(e);
    }
}

async function deleteCronJob(id) {
    if (!confirm("Delete this scheduled crontab automation?")) return;
    try {
        const res = await fetch(`/api/admin/cron/${id}`, { method: "DELETE" });
        const json = await res.json();
        if (json.success) fetchCronJobsList();
    } catch (e) {
        console.error(e);
    }
}

async function runCronNow(id) {
    try {
        const res = await fetch(`/api/admin/cron/run-now/${id}`, { method: "POST" });
        const json = await res.json();
        alert(json.message);
        fetchCronJobsList();
    } catch (e) {
        alert("Execution error: " + e.message);
    }
}

/* =====================================================================
   CUSTOM DATA RANGE & REAL EMAIL DISPATCH
   ===================================================================== */
function populateCustomServicesChecklist(services) {
    const container = document.getElementById("customServicesChecklist");
    if (!container) return;
    container.innerHTML = "";

    const items = services || (_billingData ? _billingData.services : []);
    items.forEach(s => {
        const div = document.createElement("label");
        div.className = "chk-item";
        div.innerHTML = `
            <input type="checkbox" class="service-checkbox" value="${escapeHtml(s.service)}" checked>
            <span>${escapeHtml(shortenText(s.service, 20))}</span>
        `;
        container.appendChild(div);
    });

    const today = new Date();
    const firstDay = new Date(today.getFullYear(), today.getMonth(), 1);
    const dateFrom = document.getElementById("customDateFrom");
    const dateTo = document.getElementById("customDateTo");
    if (dateFrom && !dateFrom.value) dateFrom.value = firstDay.toISOString().slice(0, 10);
    if (dateTo && !dateTo.value) dateTo.value = today.toISOString().slice(0, 10);
}

function toggleSelectAllServices() {
    const chks = document.querySelectorAll(".service-checkbox");
    const anyUnchecked = Array.from(chks).some(c => !c.checked);
    chks.forEach(c => c.checked = anyUnchecked);
}

function getSelectedServices() {
    const chks = document.querySelectorAll(".service-checkbox:checked");
    return Array.from(chks).map(c => c.value);
}

function downloadCustomReport(format = "html") {
    const dateFrom = document.getElementById("customDateFrom").value;
    const dateTo = document.getElementById("customDateTo").value;
    const selected = getSelectedServices();

    if (selected.length === 0) {
        alert("Please select at least one AWS service dimension to include.");
        return;
    }

    const data = _billingData || DEFAULT_SAMPLE_DATA;
    const filteredServices = (data.services || []).filter(s => selected.includes(s.service));
    const filteredTotal = filteredServices.reduce((sum, s) => sum + Number(s.cost || 0), 0);

    const customDataset = {
        ...data,
        current_cost: filteredTotal,
        services: filteredServices,
        period: { start: dateFrom, end: dateTo }
    };

    if (format === "html") {
        downloadExecutiveHTMLReport(customDataset, `AWS Custom Spend Report (${dateFrom} to ${dateTo})`);
    } else if (format === "pdf") {
        downloadPDFReport(customDataset);
    } else {
        downloadCSV(customDataset);
    }
}

/* REAL EMAIL DISPATCH VIA SMTP */
async function sendCustomReportEmail() {
    const recipient = document.getElementById("customEmailRecipient").value.trim();
    const dateFrom = document.getElementById("customDateFrom").value;
    const dateTo = document.getElementById("customDateTo").value;
    const subject = document.getElementById("customEmailSubject").value.trim() || `AWS Custom Spend Report (${dateFrom} to ${dateTo})`;
    const notes = document.getElementById("customEmailNotes").value.trim();
    const selected = getSelectedServices();
    const resultBox = document.getElementById("emailSendResultBox");

    if (!recipient) {
        alert("Please enter a recipient email address.");
        return;
    }
    if (selected.length === 0) {
        alert("Please select at least one AWS service dimension.");
        return;
    }

    resultBox.style.display = "block";
    resultBox.className = "email-result-box warning";
    resultBox.innerHTML = `<strong>Sending email...</strong> Contacting outgoing SMTP mail server to dispatch report to ${escapeHtml(recipient)}...`;

    // Filter services
    const data = _billingData || DEFAULT_SAMPLE_DATA;
    const filteredServices = (data.services || []).filter(s => selected.includes(s.service));
    const filteredTotal = filteredServices.reduce((sum, s) => sum + Number(s.cost || 0), 0);

    // Build rich HTML report body
    const svcListHtml = filteredServices.map((s, i) => `
        <tr>
            <td style="padding:8px 10px; border-bottom:1px solid #223048; color:#94a3b8;">${i + 1}</td>
            <td style="padding:8px 10px; border-bottom:1px solid #223048; font-weight:700; color:#f4f4f5;">${escapeHtml(s.service)}</td>
            <td style="padding:8px 10px; border-bottom:1px solid #223048; text-align:right; font-weight:700; color:#00c0f0;">${formatCurrency(s.cost)}</td>
        </tr>
    `).join("");

    const fullHtmlBody = `
    <div style="font-family:Inter,-apple-system,sans-serif; background:#0b101c; color:#f4f4f5; padding:28px; border-radius:14px; max-width:680px; margin:0 auto; border:1px solid rgba(255,255,255,0.1);">
        <div style="border-bottom:2px solid #00c0f0; padding-bottom:12px; margin-bottom:18px;">
            <h2 style="color:#00c0f0; margin:0 0 4px;">AWS Infrastructure Custom Cost Report</h2>
            <p style="color:#94a3b8; font-size:12px; margin:0;">Period: ${dateFrom} &rarr; ${dateTo} &bull; Generated: ${new Date().toLocaleString()}</p>
        </div>
        ${notes ? `<div style="background:#111a2e; padding:12px 16px; border-radius:8px; margin-bottom:16px; font-size:12px; color:#e2e8f0;">${escapeHtml(notes)}</div>` : ''}
        <div style="background:#111a2e; padding:16px; border-radius:10px; margin-bottom:20px; border-top:3px solid #00c0f0;">
            <span style="font-size:10px; font-weight:800; color:#94a3b8; text-transform:uppercase;">Selected Dimensions Accrued Spend</span>
            <div style="font-size:26px; font-weight:800; color:#00c0f0; margin-top:4px;">${formatCurrency(filteredTotal)}</div>
        </div>
        <table style="width:100%; border-collapse:collapse; font-size:12px;">
            <thead>
                <tr style="background:#0f1728;">
                    <th style="padding:8px; text-align:left; color:#94a3b8;">#</th>
                    <th style="padding:8px; text-align:left; color:#94a3b8;">Service Dimension</th>
                    <th style="padding:8px; text-align:right; color:#94a3b8;">Cost (USD)</th>
                </tr>
            </thead>
            <tbody>${svcListHtml}</tbody>
        </table>
        <p style="font-size:11px; color:#64748b; margin-top:24px; text-align:center;">AWS Billing Dashboard PRO &bull; Automated Financial Dispatch</p>
    </div>
    `;

    // CSV format content
    const csvContent = "Dimension,Cost (USD)\n" + filteredServices.map(s => `"${s.service}",${Number(s.cost).toFixed(2)}`).join("\n");

    try {
        const res = await fetch("/api/admin/reports/send-custom", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                recipient: recipient,
                date_from: dateFrom,
                date_to: dateTo,
                services: selected,
                subject: subject,
                notes: notes,
                html_content: fullHtmlBody,
                csv_content: csvContent
            })
        });

        const json = await res.json();

        if (json.success) {
            resultBox.className = "email-result-box success";
            resultBox.innerHTML = `<strong>✓ Report Dispatched!</strong> ${json.message}`;
        } else {
            // SMTP is not configured yet -> Provide clear setup instructions and mailto fallback
            resultBox.className = "email-result-box warning";
            const mailtoUrl = `mailto:${encodeURIComponent(recipient)}?subject=${encodeURIComponent(subject)}&body=${encodeURIComponent(notes + "\n\nTotal Accrued: " + formatCurrency(filteredTotal) + "\nServices:\n" + filteredServices.map(s => "- " + s.service + ": " + formatCurrency(s.cost)).join("\n"))}`;
            
            resultBox.innerHTML = `
                <strong>SMTP Server Setup Required for Direct Background Sending:</strong><br>
                ${escapeHtml(json.message || "Please configure your outgoing SMTP credentials in Tab 4 (SMTP Mail Server) to deliver live emails.")}<br>
                <div style="margin-top:8px; display:flex; gap:8px;">
                    <button class="pill-cyan-btn" onclick="switchSettingsTab('smtp')">Configure SMTP Credentials</button>
                    <a href="${mailtoUrl}" class="pill-btn pill-btn-dark" target="_blank">Open in Local Email App</a>
                </div>
            `;
        }
    } catch (e) {
        resultBox.className = "email-result-box error";
        resultBox.textContent = "Error sending report: " + e.message;
    }
}

/* =====================================================================
   SMTP CONFIGURATION MANAGEMENT
   ===================================================================== */
async function loadSmtpSettings() {
    try {
        const res = await fetch("/api/admin/smtp");
        const json = await res.json();
        if (json.success && json.config) {
            const c = json.config;
            const host = document.getElementById("smtpHost");
            const port = document.getElementById("smtpPort");
            const user = document.getElementById("smtpUsername");
            const sender = document.getElementById("smtpUsername"); // default username as sender
            const tls = document.getElementById("smtpUseTls");
            if (host) host.value = c.host || "";
            if (port) port.value = c.port || 587;
            if (user) user.value = c.username || "";
            if (tls) tls.checked = c.use_tls !== false;
        }
    } catch (e) {
        console.error("loadSmtpSettings error:", e);
    }
}

async function handleSaveSmtp(e) {
    e.preventDefault();
    const host = document.getElementById("smtpHost").value.trim();
    const port = document.getElementById("smtpPort").value;
    const user = document.getElementById("smtpUsername").value.trim();
    const pass = document.getElementById("smtpPassword").value;
    const tls = document.getElementById("smtpUseTls").checked;

    try {
        const res = await fetch("/api/admin/smtp", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                host: host,
                port: port,
                username: user,
                password: pass,
                sender_email: user,
                use_tls: tls
            })
        });
        const json = await res.json();
        alert(json.message || "SMTP configuration saved!");
    } catch (e) {
        alert("Failed to save SMTP settings: " + e.message);
    }
}

async function runSmtpTest() {
    const email = document.getElementById("testEmailTarget").value.trim();
    const statusBox = document.getElementById("smtpTestStatus");

    if (!email) {
        alert("Please enter an email address to send the verification test.");
        return;
    }

    statusBox.textContent = "Connecting to SMTP server and sending test email...";
    statusBox.style.color = "var(--cyan-accent)";

    try {
        const res = await fetch("/api/admin/smtp/test", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ test_email: email })
        });
        const json = await res.json();

        if (json.success) {
            statusBox.textContent = "✓ Test email sent successfully to " + email + "!";
            statusBox.style.color = "var(--emerald)";
        } else {
            statusBox.textContent = "Error: " + (json.error || "SMTP test failed.");
            statusBox.style.color = "var(--rose)";
        }
    } catch (e) {
        statusBox.textContent = "Connection error: " + e.message;
        statusBox.style.color = "var(--rose)";
    }
}

/* =====================================================================
   EXECUTIVE COLORFUL REPORT DOWNLOADS (HTML & PDF)
   ===================================================================== */
function generateReport(type = "monthly") {
    const data = _billingData || DEFAULT_SAMPLE_DATA;
    const container = document.getElementById("visualReportContainer");
    if (container) container.innerHTML = buildVisualReportHTML(type, data);
    openReportModal();
}

function openReportModal() {
    const modal = document.getElementById("reportModal");
    if (modal) {
        modal.classList.add("open");
        document.body.style.overflow = "hidden";
    }
}

function closeReportModal() {
    const modal = document.getElementById("reportModal");
    if (modal) {
        modal.classList.remove("open");
        document.body.style.overflow = "";
    }
}

function buildVisualReportHTML(type, data) {
    const current = Number(data.current_cost || 0);
    const previous = Number(data.previous_cost || 0);
    const diff = current - previous;
    const forecast = Number(data.forecast || 0);
    const periodStr = data.period ? `${data.period.start} → ${data.period.end}` : "Current Month";

    const rows = (data.services || []).slice(0, 10).map((s, i) => {
        const cost = Number(s.cost || 0);
        const color = BAR_COLORS[i % BAR_COLORS.length];
        const share = current > 0 ? ((cost / current) * 100).toFixed(1) : "0.0";
        return `
            <tr>
                <td style="color:#64748b; font-weight:700;">${i + 1}</td>
                <td>
                    <span style="display:inline-block; width:8px; height:8px; border-radius:50%; background:${color}; margin-right:6px;"></span>
                    <strong style="color:var(--text-1);">${escapeHtml(s.service)}</strong>
                </td>
                <td style="font-weight:700; text-align:right; color:var(--text-1);">${formatCurrency(cost)}</td>
                <td style="text-align:right; color:var(--text-3);">${share}%</td>
            </tr>
        `;
    }).join("");

    return `
        <div style="background:var(--bg-card); border-radius:12px; padding:20px; border:1px solid var(--border); margin-bottom:16px;">
            <h3 style="font-size:18px; font-weight:800; color:var(--text-1);">AWS Cloud Executive Billing Report</h3>
            <p style="font-size:11.5px; color:var(--text-3); margin-top:3px;">Period: ${periodStr} &bull; Generated: ${new Date().toLocaleString()}</p>
        </div>

        <div style="display:grid; grid-template-columns:repeat(4,1fr); gap:10px; margin-bottom:18px;">
            <div style="background:var(--bg-surface); padding:14px; border-radius:10px; border-top:3px solid #00c0f0;">
                <small style="font-size:9.5px; font-weight:800; color:var(--text-3); text-transform:uppercase;">Month to Date</small>
                <div style="font-size:20px; font-weight:800; color:#00c0f0; margin-top:4px;">${formatCurrency(current)}</div>
            </div>
            <div style="background:var(--bg-surface); padding:14px; border-radius:10px; border-top:3px solid #10b981;">
                <small style="font-size:9.5px; font-weight:800; color:var(--text-3); text-transform:uppercase;">Previous Month</small>
                <div style="font-size:20px; font-weight:800; color:#10b981; margin-top:4px;">${formatCurrency(previous)}</div>
            </div>
            <div style="background:var(--bg-surface); padding:14px; border-radius:10px; border-top:3px solid #f59e0b;">
                <small style="font-size:9.5px; font-weight:800; color:var(--text-3); text-transform:uppercase;">Forecast</small>
                <div style="font-size:20px; font-weight:800; color:#f59e0b; margin-top:4px;">${formatCurrency(forecast)}</div>
            </div>
            <div style="background:var(--bg-surface); padding:14px; border-radius:10px; border-top:3px solid #7c83fd;">
                <small style="font-size:9.5px; font-weight:800; color:var(--text-3); text-transform:uppercase;">Net Variance</small>
                <div style="font-size:20px; font-weight:800; color:#7c83fd; margin-top:4px;">${diff > 0 ? '+' : ''}${formatCurrency(diff)}</div>
            </div>
        </div>

        <table style="width:100%;">
            <thead>
                <tr>
                    <th>#</th>
                    <th>AWS Service Dimension</th>
                    <th style="text-align:right;">Cost (USD)</th>
                    <th style="text-align:right;">Share</th>
                </tr>
            </thead>
            <tbody>${rows}</tbody>
        </table>
    `;
}

function downloadExecutiveHTMLReport(customData = null, customTitle = "AWS Infrastructure Cost Analysis") {
    const data = customData || _billingData || DEFAULT_SAMPLE_DATA;
    const current = Number(data.current_cost || 0);
    const previous = Number(data.previous_cost || 0);
    const diff = current - previous;
    const forecast = Number(data.forecast || 0);
    const period = data.period ? `${data.period.start} to ${data.period.end}` : "Current Cycle";

    const servicesList = (data.services || []).map((s, i) => {
        const cost = Number(s.cost || 0);
        const color = BAR_COLORS[i % BAR_COLORS.length];
        const share = current > 0 ? ((cost / current) * 100).toFixed(1) : "0.0";
        return `
            <tr>
                <td style="padding:10px; border-bottom:1px solid #223048; color:#64748b;">${i + 1}</td>
                <td style="padding:10px; border-bottom:1px solid #223048;">
                    <span style="display:inline-block; width:8px; height:8px; border-radius:50%; background:${color}; margin-right:6px;"></span>
                    <strong style="color:#f4f4f5;">${escapeHtml(s.service)}</strong>
                </td>
                <td style="padding:10px; border-bottom:1px solid #223048; text-align:right; font-weight:700; color:#00c0f0;">${formatCurrency(cost)}</td>
                <td style="padding:10px; border-bottom:1px solid #223048; text-align:right; color:#94a3b8;">${share}%</td>
            </tr>
        `;
    }).join("");

    const fullHTML = `
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>${customTitle}</title>
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700;800&display=swap');
        * { box-sizing: border-box; margin:0; padding:0; }
        body { font-family: 'Inter', system-ui, sans-serif; background: #0b101c; color: #f4f4f5; padding: 40px; }
        .report-card { max-width: 880px; margin: 0 auto; background: #111a2e; border-radius: 16px; border: 1px solid rgba(255,255,255,0.08); padding: 32px; box-shadow: 0 10px 40px rgba(0,0,0,0.5); }
        .header { display: flex; justify-content: space-between; align-items: center; padding-bottom: 20px; border-bottom: 1px solid rgba(255,255,255,0.08); margin-bottom: 24px; }
        .header h1 { font-size: 20px; color: #00c0f0; }
        .header p { font-size: 11.5px; color: #64748b; margin-top: 3px; }
        .grid-4 { display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; margin-bottom: 24px; }
        .box { background: #0f1728; border: 1px solid rgba(255,255,255,0.06); border-radius: 10px; padding: 14px; }
        .box.cyan { border-top: 3px solid #00c0f0; }
        .box.green { border-top: 3px solid #10b981; }
        .box.amber { border-top: 3px solid #f59e0b; }
        .box.purple { border-top: 3px solid #7c83fd; }
        .box-label { font-size: 9.5px; font-weight: 800; color: #64748b; text-transform: uppercase; }
        .box-val { font-size: 20px; font-weight: 800; margin-top: 4px; }
        table { width: 100%; border-collapse: collapse; font-size: 12.5px; }
        th { text-align: left; padding: 10px; background: #0f1728; font-size: 10px; text-transform: uppercase; color: #64748b; border-bottom: 1px solid #223048; }
        @media print {
            body { background: #fff !important; color: #111 !important; padding: 0; }
            .report-card { background: #fff !important; border: none; box-shadow: none; padding: 10px; }
            th { background: #f4f4f5 !important; color: #333 !important; }
            strong { color: #111 !important; }
            * { -webkit-print-color-adjust: exact !important; print-color-adjust: exact !important; }
        }
    </style>
</head>
<body>
    <div class="report-card">
        <div class="header">
            <div>
                <h1>${customTitle}</h1>
                <p>Period: ${period} &bull; Generated: ${new Date().toLocaleString()}</p>
            </div>
            <span style="background:rgba(0,192,240,0.15); color:#00c0f0; padding:4px 10px; border-radius:20px; font-size:11px; font-weight:700;">AWS PRO</span>
        </div>

        <div class="grid-4">
            <div class="box cyan">
                <div class="box-label">Month to Date</div>
                <div class="box-val" style="color:#00c0f0;">${formatCurrency(current)}</div>
            </div>
            <div class="box green">
                <div class="box-label">Previous Month</div>
                <div class="box-val" style="color:#10b981;">${formatCurrency(previous)}</div>
            </div>
            <div class="box amber">
                <div class="box-label">Forecasted Spend</div>
                <div class="box-val" style="color:#f59e0b;">${formatCurrency(forecast)}</div>
            </div>
            <div class="box purple">
                <div class="box-label">Net Variance</div>
                <div class="box-val" style="color:#7c83fd;">${diff > 0 ? '+' : ''}${formatCurrency(diff)}</div>
            </div>
        </div>

        <h4 style="margin-bottom:10px; font-size:14px;">Active Dimension Cost Breakdown</h4>
        <table>
            <thead>
                <tr>
                    <th>#</th>
                    <th>Service Dimension</th>
                    <th style="text-align:right;">Cost (USD)</th>
                    <th style="text-align:right;">Share</th>
                </tr>
            </thead>
            <tbody>${servicesList}</tbody>
        </table>
    </div>
</body>
</html>
    `;

    downloadFile(`aws-report-${new Date().toISOString().slice(0, 10)}.html`, "text/html", fullHTML);
}

function downloadPDFReport(customData = null) {
    const data = customData || _billingData || DEFAULT_SAMPLE_DATA;
    const win = window.open("", "_blank");
    if (!win) {
        alert("Please allow pop-ups to print/save PDF.");
        return;
    }

    const current = Number(data.current_cost || 0);
    const previous = Number(data.previous_cost || 0);
    const servicesList = (data.services || []).map((s, i) => `
        <tr>
            <td style="padding:6px; border-bottom:1px solid #ddd;">${i + 1}</td>
            <td style="padding:6px; border-bottom:1px solid #ddd; font-weight:600;">${escapeHtml(s.service)}</td>
            <td style="padding:6px; border-bottom:1px solid #ddd; text-align:right; font-weight:700;">${formatCurrency(s.cost)}</td>
        </tr>
    `).join("");

    win.document.write(`
        <!DOCTYPE html><html><head><title>AWS Billing PDF Report</title>
        <style>
            @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700;800&display=swap');
            * { box-sizing: border-box; -webkit-print-color-adjust: exact; print-color-adjust: exact; }
            body { font-family: 'Inter', sans-serif; padding: 24px; color: #111; }
            .hdr { border-bottom: 2px solid #00c0f0; padding-bottom: 10px; margin-bottom: 16px; }
            .stats { display: flex; gap: 12px; margin-bottom: 16px; }
            .box { flex: 1; border: 1px solid #ccc; border-top: 3px solid #00c0f0; padding: 10px; border-radius: 6px; }
            table { width: 100%; border-collapse: collapse; font-size: 11px; }
            th { text-align: left; padding: 6px; background: #eee; }
        </style></head><body>
            <div class="hdr">
                <h2>AWS Infrastructure Cost Report</h2>
                <small>Generated: ${new Date().toLocaleString()}</small>
            </div>
            <div class="stats">
                <div class="box">
                    <small>CURRENT SPEND</small>
                    <h3>${formatCurrency(current)}</h3>
                </div>
                <div class="box" style="border-top-color:#10b981;">
                    <small>PREVIOUS MONTH</small>
                    <h3 style="color:#10b981;">${formatCurrency(previous)}</h3>
                </div>
            </div>
            <h4>Resource Dimensions</h4>
            <table>
                <thead><tr><th>#</th><th>Dimension</th><th style="text-align:right;">Cost (USD)</th></tr></thead>
                <tbody>${servicesList}</tbody>
            </table>
            <script>window.onload = function() { window.print(); };</script>
        </body></html>
    `);
    win.document.close();
}

function downloadCSV(customData = null) {
    const data = customData || _billingData || DEFAULT_SAMPLE_DATA;
    const rows = [["Dimension", "Cost (USD)"], []];
    (data.services || []).forEach(s => {
        rows.push([s.service, Number(s.cost || 0).toFixed(2)]);
    });
    const csv = rows.map(r => r.map(c => `"${String(c).replace(/"/g, '""')}"`).join(",")).join("\n");
    downloadFile("aws-billing-data.csv", "text/csv", csv);
}

/* =====================================================================
   UTILITY HELPERS
   ===================================================================== */
function formatCurrency(val) {
    return "$" + Number(val || 0).toLocaleString("en-US", {
        minimumFractionDigits: 2,
        maximumFractionDigits: 2
    });
}

function formatDateShort(str) {
    if (!str) return "";
    const d = new Date(str + "T00:00:00");
    return d.toLocaleDateString("en-US", { month: "short", day: "numeric" });
}

function shortenText(txt, len) {
    if (!txt) return "";
    return txt.length > len ? txt.substring(0, len - 1) + "…" : txt;
}

function escapeHtml(str) {
    const div = document.createElement("div");
    div.textContent = str;
    return div.innerHTML;
}

function downloadFile(filename, type, content) {
    const blob = new Blob([content], { type: type });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    setTimeout(() => URL.revokeObjectURL(url), 4000);
}
