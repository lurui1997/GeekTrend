const formatPercent = (value) => {
  if (typeof value !== "number") return "n/a";
  return `${Math.round(value * 1000) / 10}%`;
};

const labelFromDate = (value) => {
  if (!value) return "unknown";
  return String(value).replace("T", " ").slice(5, 16);
};

const text = (value, fallback = "unknown") => {
  if (value === null || value === undefined || value === "") return fallback;
  return String(value);
};

const array = (value) => Array.isArray(value) ? value : [];

const renderBars = (target, rows, labelKey, valueKey, formatter = String) => {
  const element = document.querySelector(target);
  element.innerHTML = "";
  if (!rows.length) {
    const empty = document.createElement("p");
    empty.className = "empty-state";
    empty.textContent = "No signal detected in this snapshot.";
    element.appendChild(empty);
    return;
  }
  const max = Math.max(1, ...rows.map((row) => Number(row[valueKey]) || 0));
  rows.forEach((row, index) => {
    const value = Number(row[valueKey]) || 0;
    const label = text(row[labelKey]);
    const item = document.createElement("div");
    item.className = "bar-row";
    item.style.setProperty("--delay", `${index * 45}ms`);

    const labelElement = document.createElement("span");
    labelElement.className = "bar-label";
    labelElement.title = label;
    labelElement.textContent = label;

    const track = document.createElement("span");
    track.className = "bar-track";
    const fill = document.createElement("span");
    fill.className = "bar-fill";
    fill.style.width = `${(value / max) * 100}%`;
    track.appendChild(fill);

    const strong = document.createElement("strong");
    strong.textContent = formatter(row[valueKey]);

    item.append(labelElement, track, strong);
    element.appendChild(item);
  });
};

const renderTable = (repositories) => {
  const body = document.querySelector("#repo-table");
  body.innerHTML = "";
  for (const repo of repositories) {
    const agentContributors = Array.isArray(repo.ai_agent_contributors)
      ? repo.ai_agent_contributors
      : [];
    const row = document.createElement("tr");
    row.className = repo.uses_ai_agent ? "agent-hit" : "quiet-row";
    const nameCell = document.createElement("td");
    const link = document.createElement("a");
    link.href = text(repo.url, "#");
    link.textContent = text(repo.repository_name, "unknown/repository");
    const breakElement = document.createElement("br");
    const description = document.createElement("small");
    description.textContent = text(repo.description, "");
    nameCell.append(link, breakElement, description);

    const languageCell = document.createElement("td");
    languageCell.textContent = text(repo.primary_language);

    const agentCell = document.createElement("td");
    if (agentContributors.length) {
      for (const agent of agentContributors) {
        const pill = document.createElement("span");
        pill.className = "pill";
        pill.textContent = agent;
        agentCell.appendChild(pill);
      }
    } else {
      agentCell.textContent = "未检测到";
    }

    const countryCell = document.createElement("td");
    countryCell.textContent = text(repo.origin_country);

    const confidenceCell = document.createElement("td");
    confidenceCell.textContent = text(repo.origin_confidence);

    row.append(nameCell, languageCell, agentCell, countryCell, confidenceCell);
    body.appendChild(row);
  }
};

const main = async () => {
  const response = await fetch("data/summary.json", { cache: "no-store" });
  if (!response.ok) throw new Error(`Failed to load summary: ${response.status}`);
  const summary = await response.json();
  const latest = summary.latest || {};
  const history = array(summary.history);
  const agentLeaderboard = array(summary.agent_leaderboard);
  const countryDistribution = array(summary.country_distribution);
  const latestRepositories = array(summary.latest_repositories);
  const ratio = typeof latest.ai_agent_project_ratio === "number"
    ? latest.ai_agent_project_ratio
    : 0;
  const topAgent = agentLeaderboard[0];

  document.querySelector("#fetched-at").textContent = latest.fetched_at || "n/a";
  document.querySelector("#repo-count").textContent = latest.repository_count ?? "n/a";
  document.querySelector("#agent-count").textContent = latest.ai_agent_project_count ?? "n/a";
  document.querySelector("#agent-ratio").textContent = formatPercent(ratio);
  document.querySelector("#snapshot-count").textContent = summary.snapshot_count ?? "n/a";
  document.querySelector("#latest-path").textContent = summary.latest_snapshot_path || "";
  document.querySelector("#top-agent").textContent = topAgent
    ? `${topAgent.agent}`
    : "none";
  document.querySelector("#ratio-radar").style.setProperty("--ratio", ratio);

  renderBars(
    "#history-chart",
    history.slice(-12).map((row) => ({
      label: labelFromDate(row.fetched_at),
      ratio: typeof row.ai_agent_project_ratio === "number" ? row.ai_agent_project_ratio : 0,
    })),
    "label",
    "ratio",
    formatPercent,
  );
  renderBars("#agent-chart", agentLeaderboard, "agent", "project_count");
  renderBars("#country-chart", countryDistribution, "country", "project_count");
  renderTable(latestRepositories);
};

main().catch((error) => {
  const message = document.createElement("p");
  message.className = "load-error";
  message.textContent = error.message;
  document.body.prepend(message);
});
