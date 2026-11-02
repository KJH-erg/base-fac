import { Component, onWillStart, signal, useProps } from "@odoo/owl";
import { _t } from "@web/core/l10n/translation";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { standardActionServiceProps } from "@web/webclient/actions/action_plugin";

const { DateTime } = luxon;

export class MesKpiDashboard extends Component {
    static template = "mes_kpi.Dashboard";
    props = useProps(standardActionServiceProps);

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        const today = DateTime.local();
        this.dateFrom = signal(today.minus({ days: 29 }).toISODate());
        this.dateTo = signal(today.toISODate());
        this.data = signal(null);
        this.cards = [
            { key: "oee", label: _t("OEE") },
            { key: "availability", label: _t("Availability") },
            { key: "performance", label: _t("Performance") },
            { key: "quality", label: _t("Quality") },
            { key: "achievement", label: _t("Plan Achievement") },
            { key: "defect_rate", label: _t("Defect Rate") },
        ];
        onWillStart(() => this.load());
    }

    async load() {
        this.data.set(
            await this.orm.call("mes.kpi.report", "get_dashboard_data", [this.dateFrom(), this.dateTo()])
        );
    }

    async onDateChange(dateSignal, ev) {
        if (!ev.target.value) {
            return;
        }
        dateSignal.set(ev.target.value);
        await this.load();
    }

    formatPercent(value) {
        return value === null || value === undefined ? "—" : `${value.toFixed(1)}%`;
    }

    formatNumber(value) {
        return Math.round(value).toLocaleString();
    }

    isBelowTarget(line) {
        return line.oee !== null && line.oee_target > 0 && line.oee < line.oee_target;
    }

    openAnalysis(line) {
        const domain = [
            ["date", ">=", this.dateFrom()],
            ["date", "<=", this.dateTo()],
        ];
        if (line) {
            domain.push(["workcenter_id", "=", line.workcenter_id]);
        }
        this.action.doAction({
            type: "ir.actions.act_window",
            name: line ? line.workcenter_name : _t("KPI Analysis"),
            res_model: "mes.kpi.report",
            views: [
                [false, "graph"],
                [false, "pivot"],
            ],
            domain,
        });
    }
}

registry.category("actions").add("mes_kpi.dashboard", MesKpiDashboard);
