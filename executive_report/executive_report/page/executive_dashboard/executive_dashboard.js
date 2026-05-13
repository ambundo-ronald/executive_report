frappe.pages["executive-dashboard"].on_page_load = function (wrapper) {
    const page = frappe.ui.make_app_page({
        parent: wrapper,
        title: __("Executive Dashboard"),
        single_column: true,
    });

    const state = {
        activeTab: "overview",
        data: null,
    };

    if (frappe.user.has_role("Executive Report Manager")) {
        page.add_inner_button(__("Settings"), () => {
            frappe.set_route("Form", "Executive Report Settings", "Executive Report Settings");
        });
    }

    page.add_inner_button(__("Refresh"), () => load_dashboard());

    const queryParams = new URLSearchParams(window.location.search);
    const defaultFromDate = queryParams.get("from_date") || frappe.datetime.add_days(frappe.datetime.get_today(), -29);
    const defaultToDate = queryParams.get("to_date") || frappe.datetime.get_today();

    const fromDate = page.add_field({
        fieldname: "from_date",
        label: __("From Date"),
        fieldtype: "Date",
        default: defaultFromDate,
        change: () => load_dashboard(),
    });

    const toDate = page.add_field({
        fieldname: "to_date",
        label: __("To Date"),
        fieldtype: "Date",
        default: defaultToDate,
        change: () => load_dashboard(),
    });

    const $root = $(`
        <div class="executive-report-page">
            <div class="executive-report-hero">
                <div>
                    <div class="executive-report-eyebrow">${__("Executive Command View")}</div>
                    <div class="executive-report-hero-title">${__("Daily performance dashboard")}</div>
                    <div class="executive-report-hero-period"></div>
                </div>
                <div class="executive-report-hero-metrics"></div>
            </div>
            <div class="executive-report-tabs"></div>
            <div class="executive-report-kpis"></div>
            <div class="executive-report-grid">
                <div class="executive-report-main"></div>
                <div class="executive-report-side"></div>
            </div>
        </div>
    `).appendTo(page.body);

    const tabs = [
        ["overview", __("Executive Overview")],
        ["sales", __("Sales")],
        ["expense", __("Expense")],
        ["profit_loss", __("Gross Profit")],
        ["system_usage", __("System Usage")],
        ["projection", __("Projection and Simulation")],
    ];

    function render_tabs() {
        const $tabs = $root.find(".executive-report-tabs").empty();
        tabs.forEach(([key, label]) => {
            $("<button>")
                .addClass("executive-report-tab")
                .toggleClass("active", state.activeTab === key)
                .text(label)
                .on("click", () => {
                    state.activeTab = key;
                    render();
                })
                .appendTo($tabs);
        });
    }

    function format_value(value, fieldtype) {
        if (fieldtype === "Currency") {
            return format_currency(value || 0, state.data.currency);
        }
        if (fieldtype === "Percent") {
            return `${flt(value || 0, 2)}%`;
        }
        if (fieldtype === "Int") {
            return cint(value || 0).toLocaleString();
        }
        if (fieldtype === "Date") {
            return value ? frappe.datetime.str_to_user(value) : "";
        }
        return value === null || value === undefined ? "" : value;
    }

    function open_route(route) {
        if (!route) return;

        frappe.route_options = route.filters || {};
        if (route.type === "Report") {
            frappe.set_route("query-report", route.report_name);
            return;
        }
        if (route.type === "List") {
            frappe.set_route("List", route.doctype, "List");
            return;
        }
        if (route.type === "Form") {
            frappe.set_route("Form", route.doctype, route.name);
        }
    }

    function render_kpis(section) {
        const $kpis = $root.find(".executive-report-kpis").empty();
        const hiddenOverviewKpis = new Set([
            __("Net Sales"),
            __("Gross Profit"),
            __("Cash and Bank Balance"),
            __("Overdue Receivables"),
        ]);
        const kpis = state.activeTab === "overview"
            ? (section.kpis || []).filter((kpi) => !hiddenOverviewKpis.has(kpi.label))
            : (section.kpis || []);

        if (!kpis.length) {
            $kpis.html(`<div class="executive-report-muted">${__("No KPI data available.")}</div>`);
            return;
        }

        kpis.forEach((kpi) => {
            const $kpi = $(`
                <div class="executive-report-kpi">
                    <div class="label"></div>
                    <div class="value"></div>
                </div>
            `)
                .find(".label").text(kpi.label).end()
                .find(".value").text(format_value(kpi.value, kpi.fieldtype)).end();

            if (["Currency", "Percent", "Float", "Int"].includes(kpi.fieldtype)) {
                const numericValue = flt(kpi.value || 0);
                $kpi.toggleClass("positive", numericValue > 0);
                $kpi.toggleClass("negative", numericValue < 0);
            }

            if (kpi.route) {
                $kpi.addClass("clickable").attr("role", "button").on("click", () => open_route(kpi.route));
            }

            $kpi.appendTo($kpis);
        });
    }

    function render_hero() {
        const overview = state.data.tabs.overview || {};
        const heroItems = [
            [__("Sales"), find_kpi(overview, __("Net Sales")), "good"],
            [__("Profit"), find_kpi(overview, __("Gross Profit")), "good"],
            [__("Cash"), find_kpi(overview, __("Cash and Bank Balance")), "neutral"],
            [__("Receivables Risk"), find_kpi(overview, __("Overdue Receivables")), "risk"],
        ];

        $root.find(".executive-report-hero-period").text(
            `${frappe.datetime.str_to_user(state.data.from_date)} - ${frappe.datetime.str_to_user(state.data.to_date)}`
        );

        const $metrics = $root.find(".executive-report-hero-metrics").empty();
        heroItems.forEach(([label, kpi, tone]) => {
            const value = kpi ? format_value(kpi.value, kpi.fieldtype) : format_value(0, "Currency");
            $(`
                <div class="executive-report-hero-metric ${tone}">
                    <div class="executive-report-mini-label"></div>
                    <div class="executive-report-hero-value"></div>
                </div>
            `)
                .find(".executive-report-mini-label").text(label).end()
                .find(".executive-report-hero-value").text(value).end()
                .appendTo($metrics);
        });
    }

    function render_table(table) {
        const $panel = $(`
            <div class="executive-report-panel">
                <div class="executive-report-panel-header"></div>
                <div class="executive-report-panel-body"></div>
            </div>
        `);
        $panel.find(".executive-report-panel-header").text(table.title);

        if (!table.rows.length) {
            $panel.find(".executive-report-panel-body").html(
                `<div class="executive-report-muted">${__("No records found for this period.")}</div>`
            );
            return $panel;
        }

        const $tableWrap = $('<div class="executive-report-table-wrap"></div>');
        const $table = $('<table class="executive-report-table"></table>').appendTo($tableWrap);
        const $thead = $("<thead><tr></tr></thead>").appendTo($table);
        table.columns.forEach((column) => $("<th>").text(column).appendTo($thead.find("tr")));

        const $tbody = $("<tbody></tbody>").appendTo($table);
        table.rows.forEach((row, rowIndex) => {
            const $tr = $("<tr></tr>").appendTo($tbody);
            const rowRoute = (table.row_routes || [])[rowIndex];
            if (rowRoute) {
                $tr.addClass("clickable").on("click", () => open_route(rowRoute));
            }
            row.forEach((cell, index) => {
                $("<td>")
                    .text(format_value(cell, table.fieldtypes[index]))
                    .appendTo($tr);
            });
        });

        $panel.find(".executive-report-panel-body").append($tableWrap);
        return $panel;
    }

    function render_chart(chart) {
        const $panel = $(`
            <div class="executive-report-panel">
                <div class="executive-report-panel-header"></div>
                <div class="executive-report-panel-body"></div>
            </div>
        `);
        $panel.find(".executive-report-panel-header").text(chart.title);

        if (!chart.points.length) {
            $panel.find(".executive-report-panel-body").html(
                `<div class="executive-report-muted">${__("No chart data available for this period.")}</div>`
            );
            return $panel;
        }

        const maxValue = Math.max(...chart.points.map((point) => Math.abs(flt(point.value || 0))));
        const $chart = $('<div class="executive-report-bar-chart"></div>');
        chart.points.forEach((point) => {
            const width = maxValue ? Math.max(3, (Math.abs(flt(point.value || 0)) / maxValue) * 100) : 0;
            const $row = $(`
                <div class="executive-report-bar-row">
                    <div class="executive-report-bar-label"></div>
                    <div class="executive-report-bar-track"><div class="executive-report-bar-fill"></div></div>
                    <div class="executive-report-bar-value"></div>
                </div>
            `);
            const label = /^\d{4}-\d{2}-\d{2}/.test(point.label || "")
                ? format_value(point.label, "Date")
                : point.label;
            $row.find(".executive-report-bar-label").text(label);
            $row.find(".executive-report-bar-fill").css("width", `${width}%`);
            $row.find(".executive-report-bar-fill").toggleClass("negative", flt(point.value || 0) < 0);
            $row.find(".executive-report-bar-value").text(format_value(point.value, chart.fieldtype));

            if (point.route) {
                $row.addClass("clickable").on("click", () => open_route(point.route));
            }

            $row.appendTo($chart);
        });

        $panel.find(".executive-report-panel-body").append($chart);
        return $panel;
    }

    function heatmap_intensity(value, maxValue) {
        if (!value || !maxValue) {
            return 0;
        }
        return Math.max(0.12, Math.min(1, value / maxValue));
    }

    function render_heatmap(heatmap) {
        const $panel = $(`
            <div class="executive-report-panel executive-report-heatmap-panel">
                <div class="executive-report-panel-header"></div>
                <div class="executive-report-panel-body"></div>
            </div>
        `);
        $panel.find(".executive-report-panel-header").text(heatmap.title);

        if (!heatmap.rows.length || !heatmap.columns.length) {
            $panel.find(".executive-report-panel-body").html(
                `<div class="executive-report-muted">${__("No sales person heatmap data found for this period.")}</div>`
            );
            return $panel;
        }

        const maxValue = Math.max(
            ...heatmap.rows.flatMap((row) => row.values.map((value) => flt(value || 0)))
        );
        const $heatmap = $('<div class="executive-report-heatmap"></div>');
        const $grid = $('<div class="executive-report-heatmap-grid"></div>').appendTo($heatmap);
        const gridColumns = `160px repeat(${heatmap.columns.length}, 34px) 110px`;
        $grid.css("grid-template-columns", gridColumns);

        $('<div class="executive-report-heatmap-heading"></div>').appendTo($grid);
        heatmap.columns.forEach((date) => {
            $("<div>")
                .addClass("executive-report-heatmap-date")
                .text(frappe.datetime.str_to_user(date).slice(0, 5))
                .attr("title", frappe.datetime.str_to_user(date))
                .appendTo($grid);
        });
        $("<div>").addClass("executive-report-heatmap-heading").text(__("Total")).appendTo($grid);

        heatmap.rows.forEach((row) => {
            $("<div>").addClass("executive-report-heatmap-person").text(row.label).appendTo($grid);
            row.values.forEach((value, index) => {
                const amount = flt(value || 0);
                const intensity = heatmap_intensity(amount, maxValue);
                $("<div>")
                    .addClass("executive-report-heatmap-cell")
                    .toggleClass("empty", !amount)
                    .css("--heatmap-alpha", intensity)
                    .attr("title", `${row.label} | ${frappe.datetime.str_to_user(heatmap.columns[index])}: ${format_value(amount, heatmap.fieldtype)}`)
                    .appendTo($grid);
            });
            $("<div>")
                .addClass("executive-report-heatmap-total")
                .text(format_value(row.total, heatmap.fieldtype))
                .appendTo($grid);
        });

        $panel.find(".executive-report-panel-body").append($heatmap);
        return $panel;
    }

    function find_kpi(section, label) {
        return (section.kpis || []).find((kpi) => kpi.label === label);
    }

    function find_table(section, title) {
        return (section.tables || []).find((table) => table.title === title);
    }

    function render_projection_snapshot(section) {
        const health = find_kpi(section, __("Company Health Score"));
        const projectedProfit = find_kpi(section, __("Projected FY Profit"));
        const minimumCash = find_kpi(section, __("Minimum Projected Cash"));
        const breakEven = find_kpi(section, __("Break-Even Monthly Revenue"));
        const scenarioTable = find_table(section, __("Scenario Comparison"));

        const healthValue = Math.max(0, Math.min(100, flt(health?.value || 0)));
        const healthState = healthValue >= 75 ? "strong" : healthValue >= 50 ? "watch" : "risk";
        const $panel = $(`
            <div class="executive-report-projection-dashboard">
                <div class="executive-report-health-card ${healthState}">
                    <div class="executive-report-health-ring">
                        <div class="executive-report-health-score"></div>
                    </div>
                    <div>
                        <div class="executive-report-mini-label">${__("Company Health")}</div>
                        <div class="executive-report-health-title"></div>
                        <div class="executive-report-muted">${__("Responds to margin, cash cover, collections, and expense pressure.")}</div>
                    </div>
                </div>
                <div class="executive-report-forecast-strip"></div>
                <div class="executive-report-scenario-strip"></div>
            </div>
        `);

        $panel.find(".executive-report-health-ring").css("--health-score", `${healthValue}%`);
        $panel.find(".executive-report-health-score").text(cint(healthValue));
        $panel.find(".executive-report-health-title").text(
            healthState === "strong" ? __("Strong outlook") : healthState === "watch" ? __("Watch closely") : __("Risk zone")
        );

        const forecastItems = [
            [__("Projected Profit"), projectedProfit, "Currency"],
            [__("Minimum Cash"), minimumCash, "Currency"],
            [__("Break-Even Revenue"), breakEven, "Currency"],
        ];
        const $forecast = $panel.find(".executive-report-forecast-strip");
        forecastItems.forEach(([label, kpi, fieldtype]) => {
            $(`
                <div class="executive-report-forecast-chip">
                    <div class="executive-report-mini-label"></div>
                    <div class="executive-report-forecast-value"></div>
                </div>
            `)
                .find(".executive-report-mini-label").text(label).end()
                .find(".executive-report-forecast-value").text(format_value(kpi?.value || 0, fieldtype)).end()
                .appendTo($forecast);
        });

        const $scenarios = $panel.find(".executive-report-scenario-strip");
        (scenarioTable?.rows || []).forEach((row) => {
            const margin = flt(row[4] || 0);
            const scenarioState = margin >= 15 ? "strong" : margin >= 5 ? "watch" : "risk";
            $(`
                <div class="executive-report-scenario-card ${scenarioState}">
                    <div class="executive-report-scenario-name"></div>
                    <div class="executive-report-scenario-profit"></div>
                    <div class="executive-report-scenario-meta"></div>
                </div>
            `)
                .find(".executive-report-scenario-name").text(row[0]).end()
                .find(".executive-report-scenario-profit").text(format_value(row[3], "Currency")).end()
                .find(".executive-report-scenario-meta").text(`${__("Margin")}: ${format_value(row[4], "Percent")} | ${__("Min Cash")}: ${format_value(row[5], "Currency")}`).end()
                .appendTo($scenarios);
        });

        return $panel;
    }

    function render_notes(section) {
        const $side = $root.find(".executive-report-side").empty();
        if (state.activeTab === "projection") {
            render_projection_controls(section, $side);
        }

        const $panel = $(`
            <div class="executive-report-panel">
                <div class="executive-report-panel-header">${__("Period")}</div>
                <div class="executive-report-panel-body"></div>
            </div>
        `).appendTo($side);

        const notes = [
            `${__("From")}: ${frappe.datetime.str_to_user(state.data.from_date)}`,
            `${__("To")}: ${frappe.datetime.str_to_user(state.data.to_date)}`,
        ].concat(section.notes || []);

        notes.forEach((note) => {
            $("<div>").addClass("executive-report-muted").text(note).appendTo($panel.find(".executive-report-panel-body"));
        });
    }

    function render_projection_controls(section, $side) {
        const simulation = section.simulation || {};
        const $panel = $(`
            <div class="executive-report-panel executive-report-simulation-panel">
                <div class="executive-report-panel-header">${__("Simulation")}</div>
                <div class="executive-report-panel-body">
                    <div class="executive-report-simulation-grid">
                        <label>
                            <span>${__("Monthly Revenue Growth %")}</span>
                            <input data-field="revenue_growth_percent" type="number" step="0.1" class="form-control">
                        </label>
                        <label>
                            <span>${__("Monthly Expense Growth %")}</span>
                            <input data-field="expense_growth_percent" type="number" step="0.1" class="form-control">
                        </label>
                        <label>
                            <span>${__("Collection Rate %")}</span>
                            <input data-field="collection_rate_percent" type="number" step="1" min="0" max="100" class="form-control">
                        </label>
                        <label>
                            <span>${__("One-Time Revenue")}</span>
                            <input data-field="one_time_revenue" type="number" step="1000" class="form-control">
                        </label>
                        <label>
                            <span>${__("One-Time Expense")}</span>
                            <input data-field="one_time_expense" type="number" step="1000" class="form-control">
                        </label>
                        <label>
                            <span>${__("Profit Target")}</span>
                            <input data-field="profit_target" type="number" step="1000" class="form-control">
                        </label>
                        <label>
                            <span>${__("Minimum Cash Balance")}</span>
                            <input data-field="minimum_cash_balance" type="number" step="1000" class="form-control">
                        </label>
                    </div>
                    <button class="btn btn-primary btn-sm executive-report-run-simulation">${__("Run Simulation")}</button>
                </div>
            </div>
        `).appendTo($side);

        Object.keys(simulation).forEach((fieldname) => {
            $panel.find(`[data-field="${fieldname}"]`).val(simulation[fieldname]);
        });

        $panel.find(".executive-report-run-simulation").on("click", () => {
            const args = { to_date: toDate.get_value() };
            $panel.find("[data-field]").each(function () {
                args[$(this).data("field")] = flt($(this).val() || 0);
            });

            frappe.call({
                method: "executive_report.executive_report.api.run_projection_simulation",
                args,
                freeze: true,
                freeze_message: __("Running projection simulation..."),
                callback: (response) => {
                    state.data.tabs.projection = response.message;
                    state.activeTab = "projection";
                    render();
                },
            });
        });
    }

    function render() {
        if (!state.data) return;

        render_hero();
        render_tabs();
        const section = state.data.tabs[state.activeTab];
        render_kpis(section);

        const $main = $root.find(".executive-report-main").empty();
        if (state.activeTab === "projection") {
            render_projection_snapshot(section).appendTo($main);
        }
        (section.charts || []).forEach((chart) => render_chart(chart).appendTo($main));
        (section.heatmaps || []).forEach((heatmap) => render_heatmap(heatmap).appendTo($main));
        const hiddenOverviewTables = new Set([
            __("Daily Sales Performance"),
            __("Sales Person Performance"),
        ]);
        const tables = state.activeTab === "overview"
            ? section.tables.filter((table) => !hiddenOverviewTables.has(table.title))
            : section.tables;
        tables.forEach((table) => render_table(table).appendTo($main));
        render_notes(section);
    }

    function load_dashboard() {
        frappe.call({
            method: "executive_report.executive_report.api.get_dashboard",
            args: {
                from_date: fromDate.get_value(),
                to_date: toDate.get_value(),
            },
            freeze: true,
            freeze_message: __("Loading executive dashboard..."),
            callback: (response) => {
                state.data = response.message;
                render();
            },
        });
    }

    load_dashboard();
};
