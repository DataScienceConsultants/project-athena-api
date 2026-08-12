(() => {
  "use strict";

  const SVG_NS = "http://www.w3.org/2000/svg";
  const state = {
    summary: null,
    series: null,
    metric: "anomaly_score",
    days: 365,
  };

  const metricConfig = {
    anomaly_score: {
      title: "Anomaly score",
      accessor: (point) => point.anomaly_score,
      format: (value) => formatNumber(value, 1),
      axis: (value) => formatNumber(value, 0),
      domain: (values) => [0, Math.max(100, ...values)],
      threshold: 70,
      thresholdLabel: "Elevated anomaly threshold · 70",
    },
    event_count: {
      title: "Daily event count",
      accessor: (point) => point.event_count,
      format: (value) => formatNumber(value, 0),
      axis: (value) => formatCompact(value),
      domain: zeroBasedDomain,
    },
    maximum_magnitude: {
      title: "Maximum magnitude",
      accessor: (point) => point.maximum_magnitude,
      format: (value) => `M ${formatNumber(value, 2)}`,
      axis: (value) => formatNumber(value, 1),
      domain: paddedDomain,
    },
    total_energy_joules: {
      title: "Total seismic energy",
      accessor: (point) => point.total_energy_joules,
      format: formatEnergy,
      axis: (value) => formatEnergy(value, true),
      domain: zeroBasedDomain,
      transform: (value) => Math.log10(Math.max(value, 1)),
      inverse: (value) => 10 ** value,
    },
    mean_depth_km: {
      title: "Mean depth",
      accessor: (point) => point.mean_depth_km,
      format: (value) => `${formatNumber(value, 1)} km`,
      axis: (value) => `${formatNumber(value, 0)} km`,
      domain: zeroBasedDomain,
    },
  };

  const elements = {
    serviceState: byId("service-state"),
    refreshButton: byId("refresh-button"),
    regionHeading: byId("region-heading"),
    catalogAsOf: byId("catalog-as-of"),
    anomalyScore: byId("anomaly-score"),
    anomalyLevel: byId("anomaly-level"),
    trendDirection: byId("trend-direction"),
    trendStrength: byId("trend-strength"),
    eventCount: byId("event-count"),
    swarmCount: byId("swarm-count"),
    executiveSummary: byId("executive-summary"),
    overallStatus: byId("overall-status"),
    periodCount: byId("period-count"),
    chart: byId("history-chart"),
    chartEmpty: byId("chart-empty"),
    chartTitle: byId("chart-title"),
    chartLatest: byId("chart-latest"),
    chartMin: byId("chart-min"),
    chartMax: byId("chart-max"),
    chartCount: byId("chart-count"),
    chartStart: byId("chart-start"),
    chartEnd: byId("chart-end"),
    chartFrequency: byId("chart-frequency"),
    errorBanner: byId("error-banner"),
    errorMessage: byId("error-message"),
    footerStatus: byId("footer-status"),
  };

  document.addEventListener("DOMContentLoaded", () => {
    bindControls();
    loadDashboard();
  });

  function byId(id) {
    return document.getElementById(id);
  }

  function bindControls() {
    elements.refreshButton.addEventListener("click", loadDashboard);

    byId("metric-selector").addEventListener("click", (event) => {
      const button = event.target.closest("[data-metric]");
      if (!button) return;
      state.metric = button.dataset.metric;
      setActiveButton("metric-selector", button);
      renderChart();
    });

    byId("range-selector").addEventListener("click", async (event) => {
      const button = event.target.closest("[data-days]");
      if (!button) return;
      state.days = button.dataset.days === "all" ? null : Number(button.dataset.days);
      setActiveButton("range-selector", button);
      await loadTimeseries();
    });
  }

  function setActiveButton(containerId, activeButton) {
    byId(containerId).querySelectorAll(".segment").forEach((button) => {
      button.classList.toggle("active", button === activeButton);
    });
  }

  async function loadDashboard() {
    setLoading(true);
    hideError();
    try {
      const [summary, series] = await Promise.all([
        fetchJSON("/summary"),
        fetchJSON(seriesUrl()),
      ]);
      state.summary = summary;
      state.series = series;
      renderSummary();
      renderChart();
      setServiceState("online", "API online");
      elements.footerStatus.textContent = `Updated ${formatDateTime(summary.catalog_as_of_utc)}`;
    } catch (error) {
      setServiceState("offline", "API unavailable");
      showError(error);
    } finally {
      setLoading(false);
    }
  }

  async function loadTimeseries() {
    setLoading(true);
    hideError();
    try {
      state.series = await fetchJSON(seriesUrl());
      renderChart();
      setServiceState("online", "API online");
    } catch (error) {
      showError(error);
    } finally {
      setLoading(false);
    }
  }

  function seriesUrl() {
    return state.days ? `/timeseries/chart?days=${state.days}` : "/timeseries/chart";
  }

  async function fetchJSON(url) {
    const response = await fetch(url, {
      headers: { Accept: "application/json" },
      cache: "no-store",
    });
    if (!response.ok) {
      let detail = `${response.status} ${response.statusText}`;
      try {
        const body = await response.json();
        detail = body?.error?.message || body?.detail || detail;
      } catch (_) {
        // The status line is sufficient when the body is not JSON.
      }
      throw new Error(detail);
    }
    return response.json();
  }

  function renderSummary() {
    const summary = state.summary;
    if (!summary) return;

    elements.regionHeading.textContent = `${summary.region_name} · ${summary.region_key}`;
    elements.catalogAsOf.textContent = formatDateTime(summary.catalog_as_of_utc);
    elements.anomalyScore.textContent = nullable(summary.latest_anomaly_score, (value) => formatNumber(value, 1));
    elements.anomalyLevel.textContent = humanize(summary.latest_anomaly_level);
    elements.trendDirection.textContent = humanize(summary.trend_direction);
    elements.trendStrength.textContent = humanize(summary.trend_strength);
    elements.eventCount.textContent = nullable(summary.source_event_count, formatInteger);
    elements.swarmCount.textContent = nullable(summary.swarm_count, formatInteger);
    elements.executiveSummary.textContent = summary.executive_summary || "No executive summary is available.";
    elements.overallStatus.textContent = humanize(summary.overall_status);

    const level = String(summary.latest_anomaly_level || "").toLowerCase();
    elements.anomalyLevel.dataset.level = level;
  }

  function renderChart() {
    const series = state.series;
    const config = metricConfig[state.metric];
    elements.chartTitle.textContent = config.title;
    clearSvg(elements.chart);

    if (!series || !Array.isArray(series.points)) {
      setChartEmpty(true);
      resetChartStats();
      return;
    }

    const plotted = series.points.map((point, index) => ({
      point,
      index,
      value: finiteOrNull(config.accessor(point)),
    }));
    const valid = plotted.filter((item) => item.value !== null);

    elements.periodCount.textContent = formatInteger(series.available_period_count ?? series.points.length);
    elements.chartStart.textContent = formatDate(series.analysis_start || series.points.at(0)?.date);
    elements.chartEnd.textContent = formatDate(series.analysis_end || series.points.at(-1)?.date);
    elements.chartFrequency.textContent = `${capitalize(series.frequency || "daily")} historical observations`;

    if (!valid.length) {
      setChartEmpty(true);
      resetChartStats();
      return;
    }

    setChartEmpty(false);
    renderChartStats(valid.map((item) => item.value), config);
    drawChart(plotted, valid, config);
  }

  function drawChart(plotted, valid, config) {
    const width = 960;
    const height = 360;
    const margin = { top: 18, right: 18, bottom: 24, left: 62 };
    const plotWidth = width - margin.left - margin.right;
    const plotHeight = height - margin.top - margin.bottom;
    const rawValues = valid.map((item) => item.value);
    const rawDomain = config.domain(rawValues);
    const transform = config.transform || ((value) => value);
    const inverse = config.inverse || ((value) => value);
    let domainMin = transform(rawDomain[0]);
    let domainMax = transform(rawDomain[1]);

    if (!Number.isFinite(domainMin) || !Number.isFinite(domainMax) || domainMin === domainMax) {
      domainMin = 0;
      domainMax = 1;
    }

    const x = (index) => margin.left + (plotted.length <= 1 ? plotWidth / 2 : (index / (plotted.length - 1)) * plotWidth);
    const y = (value) => margin.top + (1 - ((transform(value) - domainMin) / (domainMax - domainMin))) * plotHeight;

    const defs = svg("defs");
    const gradient = svg("linearGradient", { id: "chart-area-gradient", x1: "0", y1: "0", x2: "0", y2: "1" });
    gradient.append(
      svg("stop", { offset: "0%", "stop-color": "#65d7d1", "stop-opacity": "0.18" }),
      svg("stop", { offset: "100%", "stop-color": "#65d7d1", "stop-opacity": "0" }),
    );
    defs.append(gradient);
    elements.chart.append(defs);

    for (let step = 0; step <= 4; step += 1) {
      const ratio = step / 4;
      const yPos = margin.top + ratio * plotHeight;
      const transformedValue = domainMax - ratio * (domainMax - domainMin);
      const rawValue = inverse(transformedValue);
      elements.chart.append(svg("line", {
        x1: margin.left,
        x2: width - margin.right,
        y1: yPos,
        y2: yPos,
        class: "chart-grid-line",
      }));
      const label = svg("text", {
        x: margin.left - 10,
        y: yPos + 4,
        "text-anchor": "end",
        class: "chart-axis-label",
      });
      label.textContent = config.axis(rawValue);
      elements.chart.append(label);
    }

    if (config.threshold !== undefined && config.threshold >= rawDomain[0] && config.threshold <= rawDomain[1]) {
      const thresholdY = y(config.threshold);
      elements.chart.append(svg("line", {
        x1: margin.left,
        x2: width - margin.right,
        y1: thresholdY,
        y2: thresholdY,
        class: "chart-threshold",
      }));
      const label = svg("text", {
        x: width - margin.right,
        y: thresholdY - 7,
        "text-anchor": "end",
        class: "chart-threshold-label",
      });
      label.textContent = config.thresholdLabel;
      elements.chart.append(label);
    }

    const segments = contiguousSegments(plotted);
    for (const segment of segments) {
      if (!segment.length) continue;
      const linePath = segment
        .map((item, segmentIndex) => `${segmentIndex === 0 ? "M" : "L"}${x(item.index).toFixed(2)},${y(item.value).toFixed(2)}`)
        .join(" ");

      if (segment.length > 1) {
        const first = segment[0];
        const last = segment.at(-1);
        const areaPath = `${linePath} L${x(last.index).toFixed(2)},${(margin.top + plotHeight).toFixed(2)} L${x(first.index).toFixed(2)},${(margin.top + plotHeight).toFixed(2)} Z`;
        elements.chart.append(svg("path", { d: areaPath, class: "chart-area" }));
      }
      elements.chart.append(svg("path", { d: linePath, class: "chart-path" }));
    }

    const latest = valid.at(-1);
    elements.chart.append(svg("circle", {
      cx: x(latest.index),
      cy: y(latest.value),
      r: 5,
      class: "chart-last-point",
    }));
  }

  function contiguousSegments(plotted) {
    const segments = [];
    let current = [];
    for (const item of plotted) {
      if (item.value === null) {
        if (current.length) segments.push(current);
        current = [];
      } else {
        current.push(item);
      }
    }
    if (current.length) segments.push(current);
    return segments;
  }

  function renderChartStats(values, config) {
    const latest = values.at(-1);
    const minimum = Math.min(...values);
    const maximum = Math.max(...values);
    elements.chartLatest.textContent = config.format(latest);
    elements.chartMin.textContent = config.format(minimum);
    elements.chartMax.textContent = config.format(maximum);
    elements.chartCount.textContent = formatInteger(values.length);
  }

  function resetChartStats() {
    [elements.chartLatest, elements.chartMin, elements.chartMax, elements.chartCount].forEach((element) => {
      element.textContent = "—";
    });
  }

  function setChartEmpty(empty) {
    elements.chartEmpty.hidden = !empty;
    elements.chart.hidden = empty;
  }

  function setLoading(loading) {
    elements.refreshButton.disabled = loading;
    elements.refreshButton.textContent = loading ? "Loading…" : "Refresh data";
    if (loading) setServiceState("loading", "Connecting");
  }

  function setServiceState(stateName, label) {
    elements.serviceState.dataset.state = stateName;
    const labelNode = elements.serviceState.querySelector("span:last-child");
    if (labelNode) labelNode.textContent = label;
  }

  function showError(error) {
    elements.errorMessage.textContent = error instanceof Error ? error.message : String(error);
    elements.errorBanner.hidden = false;
  }

  function hideError() {
    elements.errorBanner.hidden = true;
  }

  function clearSvg(element) {
    while (element.firstChild) element.removeChild(element.firstChild);
  }

  function svg(tag, attributes = {}) {
    const element = document.createElementNS(SVG_NS, tag);
    for (const [name, value] of Object.entries(attributes)) {
      element.setAttribute(name, String(value));
    }
    return element;
  }

  function finiteOrNull(value) {
    const number = Number(value);
    return value !== null && value !== undefined && Number.isFinite(number) ? number : null;
  }

  function zeroBasedDomain(values) {
    return [0, Math.max(...values, 1) * 1.08];
  }

  function paddedDomain(values) {
    const minimum = Math.min(...values);
    const maximum = Math.max(...values);
    if (minimum === maximum) {
      return [Math.max(0, minimum - 0.5), maximum + 0.5];
    }
    const padding = (maximum - minimum) * 0.12;
    return [Math.max(0, minimum - padding), maximum + padding];
  }

  function nullable(value, formatter) {
    return value === null || value === undefined ? "—" : formatter(value);
  }

  function formatNumber(value, digits = 1) {
    return Number(value).toLocaleString(undefined, {
      minimumFractionDigits: digits,
      maximumFractionDigits: digits,
    });
  }

  function formatInteger(value) {
    return Number(value).toLocaleString(undefined, { maximumFractionDigits: 0 });
  }

  function formatCompact(value) {
    return Number(value).toLocaleString(undefined, {
      notation: "compact",
      maximumFractionDigits: 1,
    });
  }

  function formatEnergy(value, compact = false) {
    const number = Number(value);
    if (!Number.isFinite(number)) return "—";
    if (number === 0) return "0 J";
    if (compact) {
      const exponent = Math.floor(Math.log10(Math.abs(number)));
      return `1e${exponent}`;
    }
    return `${number.toExponential(2)} J`;
  }

  function formatDateTime(value) {
    if (!value) return "—";
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return String(value);
    return date.toLocaleString(undefined, {
      year: "numeric",
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
      timeZoneName: "short",
    });
  }

  function formatDate(value) {
    if (!value) return "—";
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return String(value).slice(0, 10);
    return date.toLocaleDateString(undefined, {
      year: "numeric",
      month: "short",
      day: "numeric",
    });
  }

  function humanize(value) {
    if (value === null || value === undefined || value === "") return "—";
    return String(value).replaceAll("_", " ");
  }

  function capitalize(value) {
    const text = String(value || "");
    return text ? text[0].toUpperCase() + text.slice(1) : text;
  }
})();
