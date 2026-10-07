/* ADLC Insight Hub — Enhanced Interactive SPA */
(function() {
  "use strict";
  var API = location.origin;
  var container = document.getElementById("view-container");
  var navLinks = document.querySelectorAll(".nav-link");
  var statusBadge = document.getElementById("connection-status");

  /* ═══════════════════════════════════════════════════════════════════════
     HELPERS
     ═══════════════════════════════════════════════════════════════════════ */
  function fetchJSON(path) {
    return fetch(API + path).then(function(r) {
      if (!r.ok) throw new Error(r.status + " " + r.statusText);
      return r.json();
    });
  }

  function h(tag, attrs, children) {
    var el = document.createElement(tag);
    if (attrs) Object.keys(attrs).forEach(function(k) {
      if (k === "className") el.className = attrs[k];
      else if (k === "textContent") el.textContent = attrs[k];
      else if (k === "innerHTML") el.innerHTML = attrs[k];
      else if (k.startsWith("on")) el.addEventListener(k.slice(2).toLowerCase(), attrs[k]);
      else el.setAttribute(k, attrs[k]);
    });
    if (typeof children === "string") el.textContent = children;
    else if (Array.isArray(children)) children.forEach(function(c) { if (c) el.appendChild(c); });
    return el;
  }

  function badge(text, type) {
    return h("span", {className: "badge badge-" + (type || "neutral")}, text || "");
  }

  var STATUS_BADGE = {
    DRAFT:"neutral", SCOPED:"info", PLANNED:"info", PLAN_APPROVED:"primary",
    EXECUTING:"primary", VERIFYING:"warning", INTEGRATED:"success", RELEASED:"success",
    BLOCKED:"danger", FAILED:"danger", CANCELLED:"danger", ROLLED_BACK:"danger"
  };
  var TIER_BADGE = {LOW:"success", MEDIUM:"warning", HIGH:"warning", CRITICAL:"danger"};
  var CLS_BADGE = {DECISION:"warning", FACT:"success", INFERENCE:"info", QUESTION:"danger", ASSUMPTION:"primary"};

  function statusBadge2(s) { return badge(s, STATUS_BADGE[s] || "neutral"); }
  function tierBadge(t) { return t ? badge(t, TIER_BADGE[t] || "neutral") : null; }
  function clsBadge(c) { return badge(c, CLS_BADGE[c] || "neutral"); }

  var ROLE_COLORS = {
    "product-owner":"#8b5cf6", "product-planner":"#8b5cf6",
    "architect":"#3b82f6", "developer":"#10b981",
    "qa-derive":"#f97316", "qa-diagnose":"#f97316", "test-engineer":"#f97316",
    "code-reviewer":"#ec4899", "security-reviewer":"#ef4444",
    "system":"#64748b", "SYSTEM":"#64748b", "HUMAN":"#8b5cf6",
    "human:tech-lead":"#8b5cf6", "human:security-lead":"#ef4444",
    "human:product-owner":"#8b5cf6", "human:release-manager":"#6366f1"
  };
  function roleColor(r) { return ROLE_COLORS[r] || "#64748b"; }
  function roleTag(r) {
    return h("span", {className: "flow-role", style: "color:" + roleColor(r) + ";background:" + roleColor(r) + "15"}, r || "system");
  }

  function timeAgo(ts) {
    if (!ts) return "-";
    var diff = Math.floor((Date.now() - new Date(ts).getTime()) / 1000);
    if (diff < 60) return diff + "s ago";
    if (diff < 3600) return Math.floor(diff / 60) + "m ago";
    if (diff < 86400) return Math.floor(diff / 3600) + "h ago";
    return Math.floor(diff / 86400) + "d ago";
  }
  function shortTime(ts) { return ts ? new Date(ts).toLocaleTimeString([], {hour:"2-digit",minute:"2-digit",second:"2-digit"}) : ""; }
  function shortDate(ts) { return ts ? new Date(ts).toLocaleDateString([], {month:"short",day:"numeric",hour:"2-digit",minute:"2-digit"}) : ""; }

  function parsePayload(p) {
    if (!p) return {};
    if (typeof p === "string") { try { return JSON.parse(p); } catch(e) { return {}; } }
    return p;
  }

  function metricCard(icon, label, value, color) {
    return h("div", {className: "metric-card fade-in"}, [
      h("div", {className: "metric-icon"}, icon),
      h("div", {className: "metric-value", style: color ? "color:" + color : ""}, String(value)),
      h("div", {className: "metric-label"}, label)
    ]);
  }

  function loading() { return h("div", {className: "empty-state"}, [h("span", {className: "loading-spinner"}), h("span", null, " Loading...")]); }

  /* ═══════════════════════════════════════════════════════════════════════
     ROUTING
     ═══════════════════════════════════════════════════════════════════════ */
  function route() {
    var hash = location.hash || "#/";
    var parts = hash.replace("#/", "").split("/");
    var view = parts[0] || "dashboard";
    var param = parts.slice(1).join("/");
    navLinks.forEach(function(a) {
      a.classList.toggle("active", a.getAttribute("data-view") === view);
    });
    switch (view) {
      case "dashboard":  renderDashboard(); break;
      case "workitems":  param ? renderWorkItemDetail(param) : renderWorkItems(); break;
      case "agents":     param ? renderAgentFlowCS(param) : renderAgentFlow(); break;
      case "evidence":   renderEvidence(); break;
      case "trace":      renderTrace(); break;
      default: container.innerHTML = ""; container.appendChild(h("div",{className:"empty-state"},"View not found"));
    }
  }
  window.addEventListener("hashchange", route);

  /* ═══════════════════════════════════════════════════════════════════════
     STAGE PIPELINE COMPONENT
     ═══════════════════════════════════════════════════════════════════════ */
  var ALL_STAGES = ["INTAKE","ARCHITECTURE","PLAN","DESIGN","IMPLEMENT","TEST","REVIEW"];

  function stagePipeline(stageHistory, currentStage) {
    var entered = {};
    var passed = {};
    var failed = {};
    (stageHistory || []).forEach(function(sh) {
      var s = sh.stage;
      if (sh.event === "stage.enter") entered[s] = true;
      if (sh.event === "stage.gate_pass") passed[s] = true;
      if (sh.event === "stage.gate_fail") failed[s] = true;
      if (sh.event === "stage.exit") passed[s] = true;
    });
    var bar = h("div", {className: "stage-pipeline"});
    ALL_STAGES.forEach(function(s, i) {
      if (i > 0) {
        var conn = h("div", {className: "stage-connector" + (passed[ALL_STAGES[i-1]] ? " done" : "")});
        bar.appendChild(conn);
      }
      var cls = "stage-node";
      var dotText = String(i + 1);
      if (failed[s]) { cls += " stage-failed"; dotText = "!"; }
      else if (s === currentStage && !passed[s]) { cls += " stage-active"; }
      else if (passed[s] || entered[s]) { cls += " stage-done"; dotText = "\u2713"; }
      bar.appendChild(h("div", {className: cls}, [
        h("div", {className: "stage-dot"}, dotText),
        h("div", {className: "stage-name"}, s)
      ]));
    });
    return bar;
  }

  /* ═══════════════════════════════════════════════════════════════════════
     TAB COMPONENT
     ═══════════════════════════════════════════════════════════════════════ */
  function tabPanel(tabs) {
    var bar = h("div", {className: "tab-bar"});
    var content = h("div");
    var activeIdx = 0;
    function activate(idx) {
      activeIdx = idx;
      bar.querySelectorAll(".tab-btn").forEach(function(b, i) { b.classList.toggle("active", i === idx); });
      content.innerHTML = "";
      if (tabs[idx] && tabs[idx].render) tabs[idx].render(content);
    }
    tabs.forEach(function(tab, i) {
      var countEl = tab.count != null ? h("span", {className: "tab-count"}, String(tab.count)) : null;
      var btn = h("button", {className: "tab-btn" + (i === 0 ? " active" : ""), onClick: function() { activate(i); }},
        countEl ? [h("span", null, tab.label), countEl] : [h("span", null, tab.label)]);
      bar.appendChild(btn);
    });
    var wrapper = h("div", null, [bar, content]);
    activate(0);
    return wrapper;
  }

  /* ═══════════════════════════════════════════════════════════════════════
     DASHBOARD
     ═══════════════════════════════════════════════════════════════════════ */
  function renderDashboard() {
    container.innerHTML = ""; container.appendChild(loading());
    Promise.all([
      fetchJSON("/api/overview"),
      fetchJSON("/api/changesets").catch(function() { return []; }),
      fetchJSON("/api/evidence?change_set_id=").catch(function() { return []; }),
      fetchJSON("/api/handoffs?change_set_id=").catch(function() { return []; }),
      fetchJSON("/api/trace?change_set_id=").catch(function() { return []; })
    ]).then(function(res) {
      var ov = res[0], cs = res[1], ev = res[2], ho = res[3], tr = res[4];
      container.innerHTML = "";

      // Header
      var hdr = h("div", {className: "page-header"});
      hdr.appendChild(h("h1", null, "Dashboard"));
      hdr.appendChild(h("div", {className: "subtitle"}, "Real-time overview of ADLC agent activity"));
      container.appendChild(hdr);

      // Metrics
      container.appendChild(h("div", {className: "metric-grid"}, [
        metricCard("\u25C6", "Change Sets", ov.change_sets, "var(--color-primary)"),
        metricCard("\u270E", "Evidence", ov.evidence, "var(--color-info)"),
        metricCard("\u2194", "Handoffs", ov.handoffs, "var(--role-architect)"),
        metricCard("\u2611", "Tasks", ov.tasks, "var(--color-success)"),
        metricCard("\u2630", "Journal Events", ov.journal_events, "var(--color-warning)"),
        metricCard("\u2605", "Active Roles", ov.roles.length, "var(--role-reviewer)")
      ]));

      // Two-column layout: change sets + activity
      var grid = h("div", {style: "display:grid;grid-template-columns:1fr 1fr;gap:var(--space-5)"});

      // Left: Change Sets
      var csCard = h("div", {className: "card"});
      csCard.appendChild(h("div", {className: "card-title"}, "Change Sets"));
      if (!cs.length) {
        csCard.appendChild(h("div", {className: "empty-state"}, "No change sets yet. Run an ADLC pipeline to see data."));
      } else {
        cs.forEach(function(item) {
          var c = h("div", {className: "cs-card", onClick: function() { location.hash = "#/workitems/" + item.id; }});
          c.appendChild(h("div", {className: "cs-header"}, [
            h("span", {className: "cs-id"}, item.id),
            statusBadge2(item.status),
            tierBadge(item.risk_tier)
          ]));
          c.appendChild(h("div", {className: "cs-title"}, item.title || "Untitled"));
          c.appendChild(h("div", {className: "cs-meta"}, "Updated " + timeAgo(item.updated_at)));
          csCard.appendChild(c);
        });
      }
      grid.appendChild(csCard);

      // Right: Recent Activity (evidence + handoffs interleaved)
      var actCard = h("div", {className: "card"});
      actCard.appendChild(h("div", {className: "card-title"}, "Recent Activity"));
      var allAct = [];
      ev.slice(0, 30).forEach(function(e) {
        allAct.push({time: e.timestamp, type: "evidence", role: e.agent_role || e.actor_type, cls: e.classification, text: e.content, cs: e.change_set_id, trust: e.trust_level});
      });
      ho.slice(0, 20).forEach(function(h2) {
        var p = parsePayload(h2.payload);
        allAct.push({time: h2.timestamp, type: "handoff", from: h2.from_role, to: h2.to_role, verdict: h2.verdict, text: p.summary || "", cs: h2.change_set_id});
      });
      tr.slice(0, 20).forEach(function(e) {
        var p = parsePayload(e.payload);
        allAct.push({time: e.timestamp, type: "trace", role: e.agent_role || e.actor_type, eventType: e.event_type, text: p.stage || p.stop_reason || e.event_type, cs: e.change_set_id});
      });
      allAct.sort(function(a, b) { return (b.time || "").localeCompare(a.time || ""); });

      if (allAct.length) {
        var tl = h("div", {className: "timeline"});
        allAct.slice(0, 40).forEach(function(item) {
          var icon, headerEls;
          if (item.type === "handoff") {
            icon = "\u2194";
            headerEls = [roleTag(item.from), h("span",{className:"flow-arrow"},"\u2192"), roleTag(item.to),
              item.verdict ? badge(item.verdict, item.verdict === "ACCEPT" ? "success" : item.verdict === "REJECT" ? "danger" : "warning") : null];
          } else if (item.type === "evidence") {
            icon = item.cls === "DECISION" ? "\u2696" : item.cls === "FACT" ? "\u2714" : "\u270E";
            headerEls = [roleTag(item.role), clsBadge(item.cls), item.trust ? badge(item.trust, "neutral") : null];
          } else {
            icon = item.eventType && item.eventType.indexOf("stage") === 0 ? "\u25B6" : "\u2022";
            headerEls = [roleTag(item.role), badge(item.eventType, "neutral")];
          }
          var entry = h("div", {className: "timeline-entry fade-in"}, [
            h("div", {className: "timeline-left"}, [
              h("div", {className: "timeline-time"}, shortTime(item.time)),
              h("div", {className: "timeline-icon"}, icon)
            ]),
            h("div", {className: "timeline-body"}, [
              h("div", {className: "timeline-header"}, headerEls),
              item.text ? h("div", {className: "timeline-content"}, String(item.text).slice(0, 200)) : null,
              item.cs ? h("div", {className: "timeline-meta"}, [h("a", {href: "#/workitems/" + item.cs, style: "color:var(--color-primary);text-decoration:none;font-size:11px"}, item.cs)]) : null
            ])
          ]);
          tl.appendChild(entry);
        });
        actCard.appendChild(tl);
      } else {
        actCard.appendChild(h("div", {className: "empty-state"}, "No activity yet."));
      }
      grid.appendChild(actCard);
      container.appendChild(grid);
    }).catch(function(err) {
      container.innerHTML = ""; container.appendChild(h("div",{className:"empty-state"},"Error: " + err.message));
    });
  }

  /* ═══════════════════════════════════════════════════════════════════════
     WORK ITEMS LIST
     ═══════════════════════════════════════════════════════════════════════ */
  function renderWorkItems() {
    container.innerHTML = ""; container.appendChild(loading());
    Promise.all([
      fetchJSON("/api/changesets"),
      fetchJSON("/api/handoffs?change_set_id=").catch(function() { return []; }),
      fetchJSON("/api/evidence?change_set_id=").catch(function() { return []; }),
      fetchJSON("/api/tasks?change_set_id=").catch(function() { return []; })
    ]).then(function(res) {
      var cs = res[0], ho = res[1], ev = res[2], tasks = res[3];
      container.innerHTML = "";
      var hdr = h("div", {className: "page-header"});
      hdr.appendChild(h("h1", null, "Work Items"));
      hdr.appendChild(h("div", {className: "subtitle"}, cs.length + " change set" + (cs.length !== 1 ? "s" : "") + " tracked"));
      container.appendChild(hdr);

      if (!cs.length) {
        container.appendChild(h("div", {className: "empty-state"}, "No change sets. Run an ADLC pipeline to create work items."));
        return;
      }

      cs.forEach(function(item) {
        var hoCount = ho.filter(function(x) { return x.change_set_id === item.id; }).length;
        var evCount = ev.filter(function(x) { return x.change_set_id === item.id; }).length;
        var taskCount = tasks.filter(function(x) { return x.change_set_id === item.id; }).length;
        var taskDone = tasks.filter(function(x) { return x.change_set_id === item.id && x.status === "DONE"; }).length;

        var card = h("div", {className: "cs-card fade-in", onClick: function() { location.hash = "#/workitems/" + item.id; }});
        card.appendChild(h("div", {className: "cs-header"}, [
          h("span", {className: "cs-id"}, item.id),
          statusBadge2(item.status),
          tierBadge(item.risk_tier)
        ]));
        card.appendChild(h("div", {className: "cs-title"}, item.title || "Untitled"));
        card.appendChild(h("div", {className: "cs-meta"}, "Created " + timeAgo(item.created_at) + " \u00B7 Updated " + timeAgo(item.updated_at)));
        card.appendChild(h("div", {className: "cs-stats"}, [
          h("span", {className: "cs-stat"}, [h("span",{className:"cs-stat-val"},String(evCount)), h("span",null," evidence")]),
          h("span", {className: "cs-stat"}, [h("span",{className:"cs-stat-val"},String(hoCount)), h("span",null," handoffs")]),
          h("span", {className: "cs-stat"}, [h("span",{className:"cs-stat-val"},String(taskDone)+"/"+String(taskCount)), h("span",null," tasks")])
        ]));
        if (taskCount > 0) {
          var pct = Math.round((taskDone / taskCount) * 100);
          var pb = h("div", {className: "progress-bar"});
          pb.appendChild(h("div", {className: "progress-fill", style: "width:" + pct + "%"}));
          card.appendChild(pb);
        }
        container.appendChild(card);
      });
    }).catch(function(err) {
      container.innerHTML = ""; container.appendChild(h("div",{className:"empty-state"},"Error: " + err.message));
    });
  }

  /* ═══════════════════════════════════════════════════════════════════════
     WORK ITEM DETAIL (drill-down)
     ═══════════════════════════════════════════════════════════════════════ */
  function renderWorkItemDetail(csId) {
    container.innerHTML = ""; container.appendChild(loading());
    Promise.all([
      fetchJSON("/api/changeset/" + csId).catch(function() { return null; }),
      fetchJSON("/api/evidence?change_set_id=" + csId).catch(function() { return []; }),
      fetchJSON("/api/trace?change_set_id=" + csId).catch(function() { return []; })
    ]).then(function(res) {
      var cs = res[0], evidence = res[1], journal = res[2];
      if (!cs) { container.innerHTML = ""; container.appendChild(h("div",{className:"empty-state"},"Change set not found: " + csId)); return; }
      container.innerHTML = "";

      // Breadcrumb
      container.appendChild(h("div", {className: "breadcrumb"}, [h("a", {href: "#/workitems"}, "Work Items"), h("span", null, " / " + csId)]));

      // Header
      var hdr = h("div", {className: "page-header"});
      hdr.appendChild(h("h1", null, cs.title || csId));
      hdr.appendChild(h("div", {className: "cs-header", style: "margin-top:var(--space-2)"}, [
        h("code", {style: "font-size:var(--text-sm);color:var(--color-primary)"}, csId),
        statusBadge2(cs.status), tierBadge(cs.risk_tier || cs.effective_risk_tier)
      ]));
      if (cs.requirements && cs.requirements.length) {
        hdr.appendChild(h("div", {className: "cs-meta", style: "margin-top:var(--space-2)"}, "Requirements: " + cs.requirements.join(", ")));
      }
      if (cs.story_refs && cs.story_refs.length) {
        hdr.appendChild(h("div", {className: "cs-meta"}, "Stories: " + cs.story_refs.join(", ")));
      }
      container.appendChild(hdr);

      // Stage pipeline from journal
      var stageHistory = [];
      var currentStage = "";
      journal.forEach(function(e) {
        var p = parsePayload(e.payload);
        if (e.event_type && e.event_type.indexOf("stage.") === 0) {
          stageHistory.push({event: e.event_type, stage: p.stage || "", at: e.timestamp});
          if (e.event_type === "stage.enter") currentStage = p.stage || "";
          if (e.event_type === "stage.exit") currentStage = "";
        }
      });
      if (stageHistory.length) {
        var pipeCard = h("div", {className: "card"});
        pipeCard.appendChild(h("div", {className: "card-title"}, "Stage Progress"));
        pipeCard.appendChild(stagePipeline(stageHistory, currentStage));
        container.appendChild(pipeCard);
      }

      // Metrics
      var handoffs = cs.handoffs || [];
      var tasks = cs.tasks || [];
      var statusHist = cs.status_history || [];
      container.appendChild(h("div", {className: "metric-grid"}, [
        metricCard("\u270E", "Evidence", evidence.length, "var(--color-info)"),
        metricCard("\u2194", "Handoffs", handoffs.length, "var(--role-architect)"),
        metricCard("\u2611", "Tasks", tasks.length, "var(--color-success)"),
        metricCard("\u2630", "Journal Events", journal.length, "var(--color-warning)"),
        metricCard("\u21C4", "Status Changes", statusHist.length, "var(--color-primary)")
      ]));

      // Tabbed sections
      var stageCount = 0;
      journal.forEach(function(e) { if (e.event_type === "stage.enter") stageCount++; });
      container.appendChild(tabPanel([
        {label: "Stage Reasoning", count: stageCount, render: function(el) { renderStageReasoning(el, evidence, journal, handoffs); }},
        {label: "Agent Flow", count: handoffs.length, render: function(el) { renderHandoffFlow(el, handoffs); }},
        {label: "Evidence", count: evidence.length, render: function(el) { renderEvidenceList(el, evidence); }},
        {label: "Timeline", count: evidence.length + journal.length, render: function(el) { renderUnifiedTimeline(el, evidence, journal); }},
        {label: "Tasks", count: tasks.length, render: function(el) { renderTaskList(el, tasks); }},
        {label: "Status History", count: statusHist.length, render: function(el) { renderStatusHistory(el, statusHist); }},
        {label: "Risk", count: (cs.risk_history || []).length, render: function(el) { renderRiskHistory(el, cs.risk_history || []); }}
      ]));
    }).catch(function(err) {
      container.innerHTML = ""; container.appendChild(h("div",{className:"empty-state"},"Error: " + err.message));
    });
  }


  /* ─── Stage Reasoning (per-stage agent thoughts) ─── */
  function renderStageReasoning(el, evidence, journal, handoffs) {
    var STAGES = ["INTAKE","ARCHITECTURE","PLAN","DESIGN","IMPLEMENT","TEST","REVIEW","INTEGRATE","RELEASE","LEARN"];
    var stageRanges = [];
    var enters = {}, exits = {};
    journal.forEach(function(e) {
      var p = parsePayload(e.payload);
      if (e.event_type === "stage.enter" && p.stage) enters[p.stage] = {time: e.timestamp, lead: p.lead_role || (p.lead_roles || []).join(", "), payload: p};
      if (e.event_type === "stage.exit" && p.stage) exits[p.stage] = {time: e.timestamp, reason: p.stop_reason || "", payload: p};
      if (e.event_type === "stage.gate_pass" && p.stage) {
        if (!exits[p.stage]) exits[p.stage] = {};
        exits[p.stage].gate = p;
      }
      if (e.event_type === "stage.gate_fail" && p.stage) {
        if (!exits[p.stage]) exits[p.stage] = {};
        exits[p.stage].gateFail = p;
      }
    });
    var activeStages = STAGES.filter(function(s) { return enters[s]; });
    if (!activeStages.length) {
      el.appendChild(h("div", {className: "empty-state"}, "No stage activity. Run an ADLC pipeline to see per-stage reasoning here."));
      return;
    }
    el.appendChild(h("div", {className: "card-subtitle"}, "What each agent thought, decided, and handed off at every stage — the full decision-making record"));

    activeStages.forEach(function(stage) {
      var stageCard = h("div", {className: "reasoning-stage"});
      var enter = enters[stage] || {};
      var exit = exits[stage] || {};
      // Stage header
      var isComplete = !!exit.time;
      var statusIcon = isComplete ? "\u2714" : exit.gateFail ? "\u2718" : "\u25CF";
      var statusColor = isComplete ? "var(--color-success)" : exit.gateFail ? "var(--color-danger)" : "var(--color-warning)";
      stageCard.appendChild(h("div", {className: "reasoning-stage-header"}, [
        h("span", {className: "reasoning-stage-icon", style: "color:" + statusColor}, statusIcon),
        h("span", {className: "reasoning-stage-name"}, stage),
        enter.lead ? h("span", {className: "reasoning-stage-lead"}, [h("span",{style:"color:var(--color-text-dim)"},"Lead: "), roleTag(enter.lead)]) : null,
        enter.time ? h("span", {className: "reasoning-stage-time"}, shortTime(enter.time) + (exit.time ? " \u2192 " + shortTime(exit.time) : " (active)")) : null
      ]));

      var body = h("div", {className: "reasoning-stage-body"});

      // Stage rationale — why this stage ended
      if (exit.reason) {
        body.appendChild(h("div", {className: "reasoning-block"}, [
          h("div", {className: "reasoning-label"}, "\u{1F4AD} Agent\'s Conclusion"),
          h("div", {className: "reasoning-text"}, exit.reason)
        ]));
      }

      // Gate results
      if (exit.gate) {
        var gateLines = [];
        if (exit.gate.code_review_verdict) gateLines.push("Code Review: " + exit.gate.code_review_verdict);
        if (exit.gate.security_review_verdict) gateLines.push("Security Review: " + exit.gate.security_review_verdict);
        if (exit.gate.gate) gateLines.push("Gate: " + exit.gate.gate);
        if (gateLines.length) {
          body.appendChild(h("div", {className: "reasoning-block reasoning-gate"}, [
            h("div", {className: "reasoning-label"}, "\u2705 Gate Result"),
            h("div", {className: "reasoning-text"}, gateLines.join("\n"))
          ]));
        }
      }
      if (exit.gateFail) {
        body.appendChild(h("div", {className: "reasoning-block reasoning-gate-fail"}, [
          h("div", {className: "reasoning-label"}, "\u274C Gate Failed"),
          h("div", {className: "reasoning-text"}, JSON.stringify(exit.gateFail, null, 2))
        ]));
      }

      // Evidence at this stage — filter by timestamp range
      var stageEvidence = evidence.filter(function(e) {
        if (!enter.time) return false;
        var t = e.timestamp || "";
        if (exit.time) return t >= enter.time && t <= exit.time;
        return t >= enter.time;
      });
      if (stageEvidence.length) {
        body.appendChild(h("div", {className: "reasoning-block"}, [
          h("div", {className: "reasoning-label"}, "\u{1F4DD} Agent Notes & Decisions (" + stageEvidence.length + ")")
        ]));
        stageEvidence.forEach(function(e) {
          var noteCard = h("div", {className: "reasoning-note cls-" + (e.classification || "")});
          noteCard.appendChild(h("div", {className: "reasoning-note-header"}, [
            clsBadge(e.classification),
            roleTag(e.agent_role || e.actor_type),
            e.source ? h("span", {style: "font-size:11px;color:var(--color-text-dim);margin-left:auto"}, e.source) : null
          ]));
          noteCard.appendChild(h("div", {className: "reasoning-note-content"}, e.content || "(no content)"));
          body.appendChild(noteCard);
        });
      }

      // Handoffs at this stage
      var stageHandoffs = handoffs.filter(function(ho) {
        if (!enter.time) return false;
        var t = ho.timestamp || "";
        if (exit.time) return t >= enter.time && t <= exit.time;
        return t >= enter.time;
      });
      if (stageHandoffs.length) {
        body.appendChild(h("div", {className: "reasoning-block"}, [
          h("div", {className: "reasoning-label"}, "\u{1F91D} Handoffs at This Stage (" + stageHandoffs.length + ")")
        ]));
        stageHandoffs.forEach(function(ho) {
          var p = parsePayload(ho.payload);
          var hoCard = h("div", {className: "reasoning-handoff"});
          hoCard.appendChild(h("div", {style: "display:flex;align-items:center;gap:var(--space-2);flex-wrap:wrap"}, [
            roleTag(ho.from_role), h("span",{style:"color:var(--color-text-dim)"},"\u2192"), roleTag(ho.to_role),
            ho.verdict ? badge(ho.verdict, ho.verdict === "ACCEPT" ? "success" : ho.verdict === "REJECT" ? "danger" : "warning") : null
          ]));
          if (p.summary) hoCard.appendChild(h("div", {className: "reasoning-text", style: "margin-top:var(--space-2)"}, p.summary));
          if (p.open_questions && p.open_questions.length) {
            hoCard.appendChild(h("div", {className: "reasoning-questions"}, [
              h("div", {className: "reasoning-sub-label"}, "\u2753 Open Questions"),
              h("ul", null, p.open_questions.map(function(q) { return h("li", null, q); }))
            ]));
          }
          if (p.pending && p.pending.length) {
            hoCard.appendChild(h("div", {className: "reasoning-pending"}, [
              h("div", {className: "reasoning-sub-label"}, "\u23F3 Pending Items"),
              h("ul", null, p.pending.map(function(item) { return h("li", null, item); }))
            ]));
          }
          if (p.inputs && p.inputs.length) {
            hoCard.appendChild(h("div", {className: "reasoning-artifacts"}, [
              h("div", {className: "reasoning-sub-label"}, "\u{1F4E5} Inputs"),
              h("ul", null, p.inputs.map(function(inp) {
                var text = typeof inp === "string" ? inp : (inp.artifact_ref || inp.ref || "");
                if (inp.description) text += " \u2014 " + inp.description;
                return h("li", {style: "word-break:break-all"}, text);
              }))
            ]));
          }
          if (p.outputs && p.outputs.length) {
            hoCard.appendChild(h("div", {className: "reasoning-artifacts"}, [
              h("div", {className: "reasoning-sub-label"}, "\u{1F4E4} Outputs"),
              h("ul", null, p.outputs.map(function(out) {
                var text = typeof out === "string" ? out : (out.artifact_ref || out.ref || "");
                if (out.description) text += " \u2014 " + out.description;
                return h("li", {style: "word-break:break-all"}, text);
              }))
            ]));
          }
          body.appendChild(hoCard);
        });
      }

      // Other journal events at this stage (not enter/exit)
      var stageJournal = journal.filter(function(e) {
        if (!enter.time) return false;
        if (e.event_type === "stage.enter" || e.event_type === "stage.exit") return false;
        var t = e.timestamp || "";
        if (exit.time) return t >= enter.time && t <= exit.time;
        return t >= enter.time;
      });
      if (stageJournal.length) {
        body.appendChild(h("div", {className: "reasoning-block"}, [
          h("div", {className: "reasoning-label"}, "\u{1F4CB} Other Events (" + stageJournal.length + ")")
        ]));
        stageJournal.forEach(function(je) {
          var p = parsePayload(je.payload);
          var jeCard = h("div", {className: "reasoning-event"});
          jeCard.appendChild(h("div", {style: "display:flex;align-items:center;gap:var(--space-2)"}, [
            badge(je.event_type, "neutral"),
            roleTag(je.agent_role || je.actor_type),
            h("span", {style: "font-size:11px;color:var(--color-text-dim);margin-left:auto"}, shortTime(je.timestamp))
          ]));
          var details = Object.keys(p).filter(function(k) { return k !== "stage"; });
          if (details.length) {
            var text = details.map(function(k) { return k + ": " + (typeof p[k] === "object" ? JSON.stringify(p[k]) : p[k]); }).join("\n");
            jeCard.appendChild(h("div", {className: "reasoning-text"}, text));
          }
          body.appendChild(jeCard);
        });
      }

      if (!body.childNodes.length) {
        body.appendChild(h("div", {style: "font-style:italic;color:var(--color-text-dim)"}, "No detailed reasoning captured for this stage."));
      }
      stageCard.appendChild(body);
      el.appendChild(stageCard);
    });
  }

  /* ─── Handoff Flow (Agent Conversation) ─── */
  function renderHandoffFlow(el, handoffs) {
    if (!handoffs.length) { el.appendChild(h("div",{className:"empty-state"},"No handoffs recorded.")); return; }
    el.appendChild(h("div", {className: "card-subtitle"}, "Shows how agents communicated back and forth \u2014 click to expand details"));
    var flow = h("div", {className: "flow-container"});
    handoffs.forEach(function(ho) {
      var p = parsePayload(ho.payload);
      var item = h("div", {className: "flow-item"});
      var dotColor = ho.verdict === "ACCEPT" ? "var(--color-success)" : ho.verdict === "REJECT" ? "var(--color-danger)" : "var(--color-primary)";
      item.appendChild(h("div", {className: "flow-dot", style: "background:" + dotColor}));
      var card = h("div", {className: "flow-card"});
      card.appendChild(h("div", {className: "flow-header"}, [
        roleTag(ho.from_role),
        h("span", {className: "flow-arrow"}, "\u2192"),
        roleTag(ho.to_role),
        ho.verdict ? badge(ho.verdict, ho.verdict === "ACCEPT" ? "success" : ho.verdict === "REJECT" ? "danger" : "warning") : null,
        ho.domain ? badge(ho.domain, "neutral") : null,
        h("span", {className: "flow-time"}, shortDate(ho.timestamp))
      ]));
      if (p.summary) card.appendChild(h("div", {className: "flow-summary"}, p.summary));
      var hasDetail = (p.inputs && p.inputs.length) || (p.outputs && p.outputs.length) || (p.open_questions && p.open_questions.length) || (p.pending && p.pending.length);
      var expandHint = h("div", {className: "flow-expand-hint"}, hasDetail ? "\u25BC Click for inputs, outputs & questions" : "");
      card.appendChild(expandHint);

      // Expandable detail
      var detail = h("div", {className: "flow-detail", style: "display:none"});
      if (p.inputs && p.inputs.length) {
        var sec = h("div", {className: "flow-detail-section"});
        sec.appendChild(h("div", {className: "flow-detail-label"}, "Inputs / Artifacts Handed Over"));
        var content = p.inputs.map(function(inp) {
          if (typeof inp === "string") return inp;
          return (inp.artifact_ref || inp.ref || "") + (inp.description ? " \u2014 " + inp.description : "");
        }).join("\n");
        sec.appendChild(h("div", {className: "flow-detail-content"}, content));
        detail.appendChild(sec);
      }
      if (p.outputs && p.outputs.length) {
        var sec2 = h("div", {className: "flow-detail-section"});
        sec2.appendChild(h("div", {className: "flow-detail-label"}, "Outputs / Deliverables"));
        var content2 = p.outputs.map(function(out) {
          if (typeof out === "string") return out;
          return (out.artifact_ref || out.ref || "") + (out.description ? " \u2014 " + out.description : "");
        }).join("\n");
        sec2.appendChild(h("div", {className: "flow-detail-content"}, content2));
        detail.appendChild(sec2);
      }
      if (p.open_questions && p.open_questions.length) {
        var sec3 = h("div", {className: "flow-detail-section"});
        sec3.appendChild(h("div", {className: "flow-detail-label"}, "Open Questions"));
        sec3.appendChild(h("div", {className: "flow-detail-content"}, p.open_questions.join("\n")));
        detail.appendChild(sec3);
      }
      if (p.pending && p.pending.length) {
        var sec4 = h("div", {className: "flow-detail-section"});
        sec4.appendChild(h("div", {className: "flow-detail-label"}, "Pending Items"));
        sec4.appendChild(h("div", {className: "flow-detail-content"}, p.pending.join("\n")));
        detail.appendChild(sec4);
      }
      // Show raw payload as fallback
      var payloadKeys = Object.keys(p).filter(function(k) { return ["summary","inputs","outputs","open_questions","pending"].indexOf(k) < 0; });
      if (payloadKeys.length) {
        var sec5 = h("div", {className: "flow-detail-section"});
        sec5.appendChild(h("div", {className: "flow-detail-label"}, "Additional Details"));
        var extra = {};
        payloadKeys.forEach(function(k) { extra[k] = p[k]; });
        sec5.appendChild(h("div", {className: "flow-detail-content"}, JSON.stringify(extra, null, 2)));
        detail.appendChild(sec5);
      }

      card.appendChild(detail);
      card.addEventListener("click", function() {
        var showing = detail.style.display !== "none";
        detail.style.display = showing ? "none" : "block";
        card.classList.toggle("expanded", !showing);
        if (hasDetail) expandHint.textContent = showing ? "\u25BC Click for inputs, outputs & questions" : "\u25B2 Hide details";
      });
      item.appendChild(card);
      flow.appendChild(item);
    });
    el.appendChild(flow);
  }

  /* ─── Evidence List ─── */
  function renderEvidenceList(el, evidence) {
    if (!evidence.length) { el.appendChild(h("div",{className:"empty-state"},"No evidence recorded.")); return; }
    el.appendChild(h("div", {className: "card-subtitle"}, "Agent notes, decisions, facts, and questions \u2014 click to expand full reasoning"));
    evidence.forEach(function(e) {
      var card = h("div", {className: "evidence-card cls-" + (e.classification || "")});
      card.appendChild(h("div", {className: "evidence-header"}, [
        clsBadge(e.classification),
        roleTag(e.agent_role || e.actor_type),
        e.source_type ? badge(e.source_type, "neutral") : null,
        e.trust_level ? badge("Trust: " + e.trust_level, "neutral") : null,
        h("span", {style: "margin-left:auto;font-size:11px;color:var(--color-text-dim)"}, shortDate(e.timestamp))
      ]));
      var contentEl = h("div", {className: "evidence-content"}, e.content || "(no content)");
      card.appendChild(contentEl);
      var expandBtn = null;
      if (e.content && e.content.length > 100) {
        expandBtn = h("div", {className: "evidence-expand"}, "\u25BC Show full reasoning");
        card.appendChild(expandBtn);
      }
      if (e.source) {
        card.appendChild(h("div", {className: "evidence-source"}, "\u2192 Source: " + e.source));
      }
      // Show extra metadata when expanded
      var meta = h("div", {className: "evidence-meta"});
      if (e.lifecycle_state) meta.appendChild(h("div", null, [h("strong",null,"Lifecycle State: "), h("span",null,e.lifecycle_state)]));
      if (e.outcome_status) meta.appendChild(h("div", null, [h("strong",null,"Outcome: "), h("span",null,e.outcome_status)]));
      if (e.model_id) meta.appendChild(h("div", null, [h("strong",null,"Model: "), h("span",null,e.model_id)]));
      if (e.change_set_id) meta.appendChild(h("div", null, [h("strong",null,"Change Set: "), h("a",{href:"#/workitems/"+e.change_set_id,style:"color:var(--color-primary)"},e.change_set_id)]));
      if (e.input_references) {
        var refs = typeof e.input_references === "string" ? e.input_references : JSON.stringify(e.input_references);
        if (refs && refs !== "null" && refs !== "[]") meta.appendChild(h("div", null, [h("strong",null,"Input Refs: "), h("span",null,refs)]));
      }
      if (e.output_references) {
        var orefs = typeof e.output_references === "string" ? e.output_references : JSON.stringify(e.output_references);
        if (orefs && orefs !== "null" && orefs !== "[]") meta.appendChild(h("div", null, [h("strong",null,"Output Refs: "), h("span",null,orefs)]));
      }
      if (meta.childNodes.length > 0) card.appendChild(meta);

      card.addEventListener("click", function(ev) {
        ev.stopPropagation();
        var isExpanded = card.classList.toggle("expanded");
        if (expandBtn) expandBtn.textContent = isExpanded ? "\u25B2 Collapse" : "\u25BC Show full reasoning";
      });
      el.appendChild(card);
    });
  }

  /* ─── Unified Timeline ─── */
  function renderUnifiedTimeline(el, evidence, journal) {
    var items = [];
    evidence.forEach(function(e) {
      items.push({
        time: e.timestamp, type: "evidence",
        icon: e.classification === "DECISION" ? "\u2696" : e.classification === "FACT" ? "\u2714" : "\u270E",
        role: e.agent_role || e.actor_type, title: e.classification + (e.source_type ? " (" + e.source_type + ")" : ""),
        content: e.content, badges: [e.trust_level ? badge("Trust: " + e.trust_level, "neutral") : null]
      });
    });
    journal.forEach(function(e) {
      var p = parsePayload(e.payload);
      var content = "";
      if (p.stage) content = "Stage: " + p.stage;
      if (p.lead_role) content += " (lead: " + p.lead_role + ")";
      if (p.lead_roles) content += " (leads: " + (p.lead_roles || []).join(", ") + ")";
      if (p.stages_completed) content = "Completed: " + (p.stages_completed || []).join(" \u2192 ");
      if (p.stop_reason) content += " | Stop: " + p.stop_reason;
      if (p.code_review_verdict) content += " | Code review: " + p.code_review_verdict;
      if (p.security_review_verdict) content += " | Security: " + p.security_review_verdict;
      if (p.rationale) content += "\nRationale: " + p.rationale;
      if (p.notes) content += "\nNotes: " + p.notes;
      if (p.gate) content += " | Gate: " + p.gate;
      if (p.error) content += " | Error: " + p.error;
      if (p.conflict_detail) content += "\nConflict: " + p.conflict_detail;
      if (p.message) content += "\nMessage: " + p.message;
      if (!content) content = JSON.stringify(p, null, 2);
      var icon = e.event_type.indexOf("stage.enter") >= 0 ? "\u25B6" :
                 e.event_type.indexOf("stage.exit") >= 0 ? "\u23F9" :
                 e.event_type.indexOf("task.") >= 0 ? "\u2611" :
                 e.event_type.indexOf("evidence.") >= 0 ? "\u270E" :
                 e.event_type.indexOf("coord.") >= 0 ? "\u2194" : "\u2022";
      items.push({
        time: e.timestamp, type: "journal", icon: icon,
        role: e.agent_role || e.actor_type, title: e.event_type,
        content: content, badges: []
      });
    });
    items.sort(function(a, b) { return (a.time || "").localeCompare(b.time || ""); });

    if (!items.length) { el.appendChild(h("div",{className:"empty-state"},"No events.")); return; }
    el.appendChild(h("div", {className: "card-subtitle"}, "All events chronologically \u2014 evidence + journal merged"));

    var tl = h("div", {className: "timeline"});
    items.forEach(function(item) {
      var headerBadges = [roleTag(item.role), badge(item.title, item.type === "evidence" ? CLS_BADGE[item.title.split(" ")[0]] || "neutral" : "neutral")];
      item.badges.forEach(function(b) { if (b) headerBadges.push(b); });
      tl.appendChild(h("div", {className: "timeline-entry fade-in"}, [
        h("div", {className: "timeline-left"}, [
          h("div", {className: "timeline-time"}, shortTime(item.time)),
          h("div", {className: "timeline-icon"}, item.icon)
        ]),
        h("div", {className: "timeline-body"}, [
          h("div", {className: "timeline-header"}, headerBadges),
          item.content ? h("div", {className: "timeline-content"}, String(item.content)) : null
        ])
      ]));
    });
    el.appendChild(tl);
  }

  /* ─── Task List ─── */
  function renderTaskList(el, tasks) {
    if (!tasks.length) { el.appendChild(h("div",{className:"empty-state"},"No tasks recorded.")); return; }
    el.appendChild(h("div", {className: "card-subtitle"}, "Task breakdown with status, owner, and dependencies"));
    tasks.forEach(function(t) {
      var card = h("div", {className: "card", style: "padding:var(--space-4)"});
      var sBadge = t.status === "DONE" ? "success" : t.status === "IN_PROGRESS" ? "primary" : t.status === "BLOCKED" ? "danger" : "neutral";
      card.appendChild(h("div", {className: "cs-header"}, [
        h("code", {style: "font-weight:600;color:var(--color-primary)"}, t.id),
        badge(t.status, sBadge),
        roleTag(t.owner_role)
      ]));
      var details = [];
      if (t.depends_on && t.depends_on.length) details.push("Depends on: " + t.depends_on.join(", "));
      if (t.ac_refs && t.ac_refs.length) details.push("AC refs: " + t.ac_refs.join(", "));
      if (t.worktree) details.push("Worktree: " + t.worktree);
      if (t.attempts > 0) details.push("Attempts: " + t.attempts);
      if (t.blocked_reason) details.push("Blocked: " + t.blocked_reason);
      if (details.length) {
        card.appendChild(h("div", {style: "font-size:var(--text-sm);color:var(--color-text-muted);margin-top:var(--space-2);line-height:1.6"}, details.join("\n")));
      }
      if (t.checkpoint) {
        card.appendChild(h("div", {style: "font-size:11px;color:var(--color-text-dim);margin-top:var(--space-2)"}, "Checkpoint: " + JSON.stringify(t.checkpoint)));
      }
      el.appendChild(card);
    });
  }

  /* ─── Status History ─── */
  function renderStatusHistory(el, history) {
    if (!history.length) { el.appendChild(h("div",{className:"empty-state"},"No status changes.")); return; }
    el.appendChild(h("div", {className: "card-subtitle"}, "Decision tree of status transitions \u2014 who changed what and why"));
    var flow = h("div", {className: "status-flow"});
    history.forEach(function(sh) {
      var step = h("div", {className: "status-step"});
      step.appendChild(h("div", {className: "status-arrow-col"}, [
        sh.from_status ? statusBadge2(sh.from_status) : badge("NEW", "neutral"),
        h("span", {className: "status-arrow"}, "\u2192"),
        statusBadge2(sh.to_status)
      ]));
      var detail = h("div", {className: "status-detail"});
      detail.appendChild(h("div", {style: "display:flex;align-items:center;gap:var(--space-2)"}, [
        h("span", {style: "font-size:var(--text-xs);color:var(--color-text-dim)"}, (sh.actor_type || "") + ":" + (sh.actor_id || "")),
        h("span", {className: "status-via"}, "via " + (sh.via || "unknown"))
      ]));
      if (sh.reason) detail.appendChild(h("div", {className: "status-reason"}, sh.reason));
      step.appendChild(detail);
      step.appendChild(h("span", {className: "status-time"}, shortDate(sh.timestamp)));
      flow.appendChild(step);
    });
    el.appendChild(flow);
  }

  /* ─── Risk History ─── */
  function renderRiskHistory(el, riskHistory) {
    if (!riskHistory.length) { el.appendChild(h("div",{className:"empty-state"},"No risk assessments.")); return; }
    el.appendChild(h("div", {className: "card-subtitle"}, "How the risk tier was computed and changed over time"));
    riskHistory.forEach(function(r) {
      var card = h("div", {className: "card", style: "padding:var(--space-4)"});
      card.appendChild(h("div", {className: "cs-header"}, [
        badge(r.kind || "COMPUTED", r.kind === "HUMAN_OVERRIDE" ? "warning" : "neutral"),
        r.previous_tier ? tierBadge(r.previous_tier) : null,
        r.previous_tier ? h("span", {style: "color:var(--color-text-dim)"}, "\u2192") : null,
        tierBadge(r.final_tier),
        r.direction ? badge(r.direction, r.direction === "UPGRADE" ? "danger" : r.direction === "DOWNGRADE" ? "success" : "neutral") : null,
        h("span", {style: "margin-left:auto;font-size:11px;color:var(--color-text-dim)"}, shortDate(r.timestamp))
      ]));
      if (r.reason_codes && r.reason_codes.length) {
        card.appendChild(h("div", {style: "font-size:var(--text-sm);color:var(--color-text-muted);margin-top:var(--space-2)"}, "Reason codes: " + r.reason_codes.join(", ")));
      }
      var det = r.detail;
      if (det && typeof det === "object" && det.reason) {
        card.appendChild(h("div", {style: "font-size:var(--text-sm);color:var(--color-text-muted);margin-top:var(--space-1)"}, det.reason));
      }
      el.appendChild(card);
    });
  }

  /* ═══════════════════════════════════════════════════════════════════════
     AGENT FLOW (global view)
     ═══════════════════════════════════════════════════════════════════════ */
  function renderAgentFlow() {
    container.innerHTML = ""; container.appendChild(loading());
    Promise.all([
      fetchJSON("/api/handoffs?change_set_id="),
      fetchJSON("/api/changesets").catch(function() { return []; })
    ]).then(function(res) {
      var ho = res[0], cs = res[1];
      container.innerHTML = "";
      var hdr = h("div", {className: "page-header"});
      hdr.appendChild(h("h1", null, "Agent Flow"));
      hdr.appendChild(h("div", {className: "subtitle"}, "How agents communicated \u2014 handoff chains across all change sets"));
      container.appendChild(hdr);

      if (!ho.length) {
        container.appendChild(h("div", {className: "empty-state"}, "No handoffs recorded. Agent communication will appear here when roles hand off work."));
        return;
      }

      // Role interaction matrix
      var matrix = {};
      ho.forEach(function(x) {
        var key = x.from_role + " \u2192 " + x.to_role;
        if (!matrix[key]) matrix[key] = {from: x.from_role, to: x.to_role, count: 0, accepts: 0, rejects: 0};
        matrix[key].count++;
        if (x.verdict === "ACCEPT") matrix[key].accepts++;
        if (x.verdict === "REJECT") matrix[key].rejects++;
      });

      var matrixCard = h("div", {className: "card"});
      matrixCard.appendChild(h("div", {className: "card-title"}, "Role Interaction Summary"));
      var table = h("table");
      var thead = h("thead");
      thead.appendChild(h("tr", null, [h("th",null,"From"), h("th",null,"To"), h("th",null,"Count"), h("th",null,"Accepts"), h("th",null,"Rejects")]));
      table.appendChild(thead);
      var tbody = h("tbody");
      Object.keys(matrix).sort().forEach(function(key) {
        var m = matrix[key];
        tbody.appendChild(h("tr", null, [
          h("td", null, [roleTag(m.from)]),
          h("td", null, [roleTag(m.to)]),
          h("td", null, String(m.count)),
          h("td", null, m.accepts > 0 ? [badge(String(m.accepts), "success")] : [h("span",null,"-")]),
          h("td", null, m.rejects > 0 ? [badge(String(m.rejects), "danger")] : [h("span",null,"-")])
        ]));
      });
      table.appendChild(tbody);
      matrixCard.appendChild(table);
      container.appendChild(matrixCard);

      // Per-CS handoff flows
      var byCS = {};
      ho.forEach(function(x) {
        if (!byCS[x.change_set_id]) byCS[x.change_set_id] = [];
        byCS[x.change_set_id].push(x);
      });

      Object.keys(byCS).forEach(function(csId) {
        var csInfo = cs.find(function(c) { return c.id === csId; }) || {};
        var card = h("div", {className: "card"});
        card.appendChild(h("div", {className: "card-header"}, [
          h("div", {className: "card-title"}, [h("a", {href: "#/workitems/" + csId, style: "color:var(--color-primary);text-decoration:none"}, csId + ": " + (csInfo.title || ""))]),
          h("div", null, [badge(byCS[csId].length + " handoffs", "primary")])
        ]));
        renderHandoffFlow(card, byCS[csId]);
        container.appendChild(card);
      });
    }).catch(function(err) {
      container.innerHTML = ""; container.appendChild(h("div",{className:"empty-state"},"Error: " + err.message));
    });
  }

  function renderAgentFlowCS(csId) {
    renderWorkItemDetail(csId);
  }

  /* ═══════════════════════════════════════════════════════════════════════
     EVIDENCE (global)
     ═══════════════════════════════════════════════════════════════════════ */
  function renderEvidence() {
    container.innerHTML = ""; container.appendChild(loading());
    fetchJSON("/api/evidence?change_set_id=").then(function(evidence) {
      container.innerHTML = "";
      var hdr = h("div", {className: "page-header"});
      hdr.appendChild(h("h1", null, "Evidence Explorer"));
      hdr.appendChild(h("div", {className: "subtitle"}, evidence.length + " evidence entries across all change sets"));
      container.appendChild(hdr);

      if (!evidence.length) {
        container.appendChild(h("div", {className: "empty-state"}, "No evidence. Agent decisions, facts, and notes will appear here."));
        return;
      }

      // Group by classification
      var groups = {};
      evidence.forEach(function(e) {
        var cls = e.classification || "UNKNOWN";
        if (!groups[cls]) groups[cls] = [];
        groups[cls].push(e);
      });

      // Metrics
      var metrics = h("div", {className: "metric-grid"});
      ["DECISION","FACT","INFERENCE","QUESTION","ASSUMPTION"].forEach(function(cls) {
        if (groups[cls]) {
          metrics.appendChild(metricCard(
            cls === "DECISION" ? "\u2696" : cls === "FACT" ? "\u2714" : cls === "QUESTION" ? "\u2753" : "\u270E",
            cls, groups[cls].length,
            cls === "DECISION" ? "var(--color-warning)" : cls === "FACT" ? "var(--color-success)" : cls === "QUESTION" ? "var(--color-danger)" : "var(--color-info)"
          ));
        }
      });
      container.appendChild(metrics);

      // Role breakdown
      var byRole = {};
      evidence.forEach(function(e) {
        var r = e.agent_role || e.actor_type || "system";
        if (!byRole[r]) byRole[r] = 0;
        byRole[r]++;
      });
      var roleCard = h("div", {className: "card"});
      roleCard.appendChild(h("div", {className: "card-title"}, "Evidence by Role"));
      var roleGrid = h("div", {style: "display:flex;gap:var(--space-4);flex-wrap:wrap"});
      Object.keys(byRole).sort(function(a,b) { return byRole[b] - byRole[a]; }).forEach(function(r) {
        roleGrid.appendChild(h("div", {style: "display:flex;align-items:center;gap:var(--space-2)"}, [roleTag(r), h("span",{style:"font-weight:700"},String(byRole[r]))]));
      });
      roleCard.appendChild(roleGrid);
      container.appendChild(roleCard);

      // All evidence
      var listCard = h("div", {className: "card"});
      listCard.appendChild(h("div", {className: "card-title"}, "All Evidence"));
      renderEvidenceList(listCard, evidence);
      container.appendChild(listCard);
    }).catch(function(err) {
      container.innerHTML = ""; container.appendChild(h("div",{className:"empty-state"},"Error: " + err.message));
    });
  }

  /* ═══════════════════════════════════════════════════════════════════════
     TRACE (global)
     ═══════════════════════════════════════════════════════════════════════ */
  function renderTrace() {
    container.innerHTML = ""; container.appendChild(loading());
    Promise.all([
      fetchJSON("/api/trace?change_set_id="),
      fetchJSON("/api/evidence?change_set_id=").catch(function() { return []; })
    ]).then(function(res) {
      var events = res[0], evidence = res[1];
      container.innerHTML = "";
      var hdr = h("div", {className: "page-header"});
      hdr.appendChild(h("h1", null, "Trace Explorer"));
      hdr.appendChild(h("div", {className: "subtitle"}, events.length + " journal events, " + evidence.length + " evidence entries"));
      container.appendChild(hdr);

      if (!events.length && !evidence.length) {
        container.appendChild(h("div", {className: "empty-state"}, "No trace data. Run an ADLC pipeline to see agent activity here."));
        return;
      }

      // Group by role for swimlanes
      var roles = {};
      events.forEach(function(e) {
        var r = e.agent_role || e.actor_type || "system";
        if (!roles[r]) roles[r] = [];
        var p = parsePayload(e.payload);
        roles[r].push({type: e.event_type, time: e.timestamp, payload: p, cs: e.change_set_id});
      });
      evidence.forEach(function(e) {
        var r = e.agent_role || e.actor_type || "system";
        if (!roles[r]) roles[r] = [];
        roles[r].push({type: e.classification, time: e.timestamp, content: e.content, cs: e.change_set_id});
      });

      // Metrics
      container.appendChild(h("div", {className: "metric-grid"}, [
        metricCard("\u2630", "Journal Events", events.length, "var(--color-warning)"),
        metricCard("\u270E", "Evidence", evidence.length, "var(--color-info)"),
        metricCard("\u2605", "Active Roles", Object.keys(roles).length, "var(--role-reviewer)")
      ]));

      // Swimlane
      var swimCard = h("div", {className: "card"});
      swimCard.appendChild(h("div", {className: "card-title"}, "Agent Swimlanes"));
      swimCard.appendChild(h("div", {className: "card-subtitle"}, "Events grouped by agent role \u2014 scroll horizontally to see all roles"));
      var swimlane = h("div", {className: "swimlane"});
      Object.keys(roles).sort().forEach(function(role) {
        var lane = h("div", {className: "lane"});
        lane.appendChild(h("div", {className: "lane-header", style: "border-color:" + roleColor(role)}, role));
        roles[role].sort(function(a, b) { return (a.time || "").localeCompare(b.time || ""); });
        roles[role].forEach(function(item) {
          var node = h("div", {className: "trace-node"});
          node.appendChild(h("strong", {style: "font-size:var(--text-xs)"}, item.type));
          if (item.content) node.appendChild(h("div", {className: "trace-content"}, String(item.content).slice(0, 160)));
          if (item.payload && item.payload.stage) node.appendChild(h("div", {className: "trace-content"}, "Stage: " + item.payload.stage));
          node.appendChild(h("div", {style: "font-size:10px;color:var(--color-text-dim);margin-top:4px"}, shortTime(item.time)));
          if (item.cs) node.appendChild(h("a", {href: "#/workitems/" + item.cs, style: "font-size:10px;color:var(--color-primary);text-decoration:none"}, item.cs));
          lane.appendChild(node);
        });
        swimlane.appendChild(lane);
      });
      swimCard.appendChild(swimlane);
      container.appendChild(swimCard);

      // Event type breakdown
      var byType = {};
      events.forEach(function(e) {
        byType[e.event_type] = (byType[e.event_type] || 0) + 1;
      });
      var typeCard = h("div", {className: "card"});
      typeCard.appendChild(h("div", {className: "card-title"}, "Event Type Distribution"));
      var typeGrid = h("div", {style: "display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:var(--space-3)"});
      Object.keys(byType).sort(function(a,b) { return byType[b] - byType[a]; }).forEach(function(t) {
        typeGrid.appendChild(h("div", {style: "display:flex;justify-content:space-between;align-items:center;padding:var(--space-2) var(--space-3);background:var(--color-surface-alt);border-radius:var(--radius-sm)"}, [
          h("span", {style: "font-size:var(--text-sm)"}, t),
          h("span", {style: "font-weight:700;color:var(--color-primary)"}, String(byType[t]))
        ]));
      });
      typeCard.appendChild(typeGrid);
      container.appendChild(typeCard);
    }).catch(function(err) {
      container.innerHTML = ""; container.appendChild(h("div",{className:"empty-state"},"Error: " + err.message));
    });
  }

  /* ═══════════════════════════════════════════════════════════════════════
     SSE
     ═══════════════════════════════════════════════════════════════════════ */
  function connectSSE() {
    try {
      var sse = new EventSource(API + "/api/events");
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
