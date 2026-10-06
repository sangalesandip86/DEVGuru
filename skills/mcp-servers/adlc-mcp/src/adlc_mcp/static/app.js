/* ADLC Insight Hub - vanilla JS SPA */
(function() {
  "use strict";

  var API = location.origin;
  var container = document.getElementById("view-container");
  var navLinks = document.querySelectorAll(".nav-link");
  var statusBadge = document.getElementById("connection-status");
  var sse = null;

  function route() {
    var hash = location.hash || "#/";
    var view = hash.replace("#/", "") || "dashboard";
    navLinks.forEach(function(a) {
      a.classList.toggle("active", a.getAttribute("data-view") === view);
    });
    switch (view) {
      case "dashboard": renderDashboard(); break;
      case "workspace": renderWorkspace(); break;
      case "workitem":  renderWorkItem(); break;
      case "trace":     renderTrace(); break;
      case "parallel":  renderParallel(); break;
      default: container.innerHTML = "<div class=empty-state>View not found</div>";
    }
  }

  window.addEventListener("hashchange", route);

  function fetchJSON(path) {
    return fetch(API + path).then(function(r) {
      if (!r.ok) throw new Error(r.statusText);
      return r.json();
    });
  }

  function h(tag, attrs, children) {
    var el = document.createElement(tag);
    if (attrs) Object.keys(attrs).forEach(function(k) {
      if (k === "className") el.className = attrs[k];
      else if (k === "textContent") el.textContent = attrs[k];
      else el.setAttribute(k, attrs[k]);
    });
    if (typeof children === "string") el.textContent = children;
    else if (Array.isArray(children)) children.forEach(function(c) { if (c) el.appendChild(c); });
    return el;
  }

  function metricCard(label, value) {
    return h("div", {className: "metric-card"}, [
      h("div", {className: "metric-value"}, String(value)),
      h("div", {className: "metric-label"}, label)
    ]);
  }

  function buildTable(caption, headers, rows) {
    var table = h("table");
    table.appendChild(h("caption", null, caption));
    var thead = h("thead");
    var tr = h("tr");
    headers.forEach(function(hdr) { tr.appendChild(h("th", {scope: "col"}, hdr)); });
    thead.appendChild(tr);
    table.appendChild(thead);
    var tbody = h("tbody");
    rows.forEach(function(row) {
      var r = h("tr");
      row.forEach(function(cell) { r.appendChild(h("td", null, String(cell || ""))); });
      tbody.appendChild(r);
    });
    table.appendChild(tbody);
    return h("div", {className: "card"}, [table]);
  }

  function renderDashboard() {
    container.innerHTML = "<div class=empty-state>Loading...</div>";
    fetchJSON("/api/health").then(function(data) {
      var grid = h("div", {className: "metric-grid"}, [
        metricCard("Uptime", Math.round(data.uptime_seconds) + "s"),
        metricCard("Modules", data.modules.length),
        metricCard("Status", data.status)
      ]);
      container.innerHTML = "";
      container.appendChild(h("h1", null, "Dashboard"));
      container.appendChild(grid);
      fetchJSON("/api/changesets").then(function(cs) {
        if (cs.length) {
          container.appendChild(buildTable("Change Sets", ["ID","Status","Risk","Updated"], cs.map(function(r) {
            return [r.id, r.status, r.risk_tier || "-", r.updated_at || "-"];
          })));
        }
      }).catch(function(){});
    }).catch(function(err) {
      container.innerHTML = "<div class=empty-state>Hub unavailable: " + err.message + "</div>";
    });
  }

  function renderWorkspace() {
    container.innerHTML = "<div class=empty-state>Loading...</div>";
    fetchJSON("/api/changesets").then(function(cs) {
      container.innerHTML = "";
      container.appendChild(h("h1", null, "Workspace"));
      if (!cs.length) { container.appendChild(h("div", {className: "empty-state"}, "No change sets")); return; }
      container.appendChild(buildTable("Change Sets", ["ID","Status","Risk","Created","Updated"], cs.map(function(r) {
        return [r.id, r.status, r.risk_tier || "-", r.created_at || "-", r.updated_at || "-"];
      })));
    }).catch(function(err) {
      container.innerHTML = "<div class=empty-state>Error: " + err.message + "</div>";
    });
  }

  function renderWorkItem() {
    container.innerHTML = "";
    container.appendChild(h("h1", null, "Work Item"));
    fetchJSON("/api/stage?change_set_id=").then(function(data) {
      if (data.graph) {
        var grid = h("div", {className: "metric-grid"});
        Object.keys(data.graph).forEach(function(s) {
          var info = data.graph[s];
          var next = (info.allowed_next || []).join(", ") || "terminal";
          grid.appendChild(h("div", {className: "metric-card"}, [
            h("div", {className: "metric-value"}, s),
            h("div", {className: "metric-label"}, "Next: " + next)
          ]));
        });
        container.appendChild(h("div", {className: "card"}, [h("div", {className: "card-title"}, "Stage Transition Graph"), grid]));
      }
    }).catch(function() {
      container.appendChild(h("div", {className: "empty-state"}, "Stage engine not available"));
    });
  }

  function renderTrace() {
    container.innerHTML = "";
    container.appendChild(h("h1", null, "Trace"));
    fetchJSON("/api/trace?change_set_id=").then(function(events) {
      if (!events.length) { container.appendChild(h("div", {className: "empty-state"}, "No trace events")); return; }
      var roles = {};
      events.forEach(function(e) {
        var role = e.agent_role || e.actor_type || "system";
        if (!roles[role]) roles[role] = [];
        roles[role].push(e);
      });
      var swimlane = h("div", {className: "swimlane"});
      Object.keys(roles).forEach(function(role) {
        var lane = h("div", {className: "lane"});
        lane.appendChild(h("div", {className: "lane-header", textContent: role}));
        roles[role].forEach(function(ev) {
          lane.appendChild(h("div", {className: "trace-node"}, [
            h("strong", null, ev.event_type),
            h("div", {className: "metric-label"}, ev.timestamp || "")
          ]));
        });
        swimlane.appendChild(lane);
      });
      container.appendChild(swimlane);
    }).catch(function() {
      container.appendChild(h("div", {className: "empty-state"}, "Journal not available"));
    });
  }

  function renderParallel() {
    container.innerHTML = "";
    container.appendChild(h("h1", null, "Parallel Execution"));
    container.appendChild(h("div", {className: "empty-state"}, "Enter a plan ID to view worker status."));
  }

  function connectSSE() {
    try {
      sse = new EventSource(API + "/api/events");
      sse.addEventListener("heartbeat", function() {
        statusBadge.textContent = "Connected";
        statusBadge.className = "badge badge-success";
      });
      sse.addEventListener("invalidate", function() { route(); });
      sse.onerror = function() {
        statusBadge.textContent = "Disconnected";
        statusBadge.className = "badge badge-danger";
      };
    } catch(e) {}
  }

  connectSSE();
  route();
})();
