from odoo import api, fields, models, tools
from odoo.tools import SQL


def _ratio(numerator, denominator):
    return numerator / denominator * 100 if denominator else None


class MesKpiReport(models.Model):
    _name = 'mes.kpi.report'
    _description = 'MES KPI Report'
    _auto = False
    _order = 'date desc'

    _depends = {
        'mes.production.plan': ['date_planned', 'workcenter_id', 'product_id', 'company_id', 'qty', 'state'],
        'mes.production.result': [
            'date', 'workcenter_id', 'product_id', 'company_id', 'state', 'output_qty', 'good_qty', 'defect_qty',
            'work_minutes', 'run_minutes', 'downtime_minutes', 'standard_minutes',
        ],
    }

    date = fields.Date(readonly=True)
    workcenter_id = fields.Many2one('mrp.workcenter', string='Line', readonly=True)
    product_id = fields.Many2one('product.product', string='Product', readonly=True)
    company_id = fields.Many2one('res.company', readonly=True)
    planned_qty = fields.Float(readonly=True)
    output_qty = fields.Float(readonly=True)
    good_qty = fields.Float(readonly=True)
    defect_qty = fields.Float(readonly=True)
    work_minutes = fields.Float(string='Elapsed (min)', readonly=True)
    run_minutes = fields.Float(string='Run (min)', readonly=True)
    downtime_minutes = fields.Float(string='Downtime (min)', readonly=True)
    standard_minutes = fields.Float(string='Standard (min)', readonly=True)
    standard_run_minutes = fields.Float(
        string='Run with Standard (min)', readonly=True,
        help="Run time of results that have a standard time, so performance only compares like with like.")

    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute(SQL("""
            CREATE VIEW %s AS (
                SELECT row_number() OVER () AS id, source.*
                FROM (
                    SELECT date_planned AS date, workcenter_id, product_id, company_id,
                           qty AS planned_qty,
                           0::float8 AS output_qty, 0::float8 AS good_qty, 0::float8 AS defect_qty,
                           0::float8 AS work_minutes, 0::float8 AS run_minutes, 0::float8 AS downtime_minutes,
                           0::float8 AS standard_minutes, 0::float8 AS standard_run_minutes
                      FROM mes_production_plan
                     WHERE state IN ('confirmed', 'done')
                    UNION ALL
                    SELECT date, workcenter_id, product_id, company_id,
                           0::float8,
                           output_qty, good_qty, defect_qty,
                           work_minutes, run_minutes, downtime_minutes,
                           standard_minutes,
                           CASE WHEN standard_minutes > 0 THEN run_minutes ELSE 0 END
                      FROM mes_production_result
                     WHERE state = 'done'
                ) source
            )""", SQL.identifier(self._table)))

    @api.model
    def _kpis_from_totals(self, totals):
        """Ratios are computed from summed quantities, never by averaging daily ratios,
        so a short day does not weigh as much as a long one. ``None`` means no data."""
        availability = _ratio(totals['run_minutes'], totals['work_minutes'])
        performance = _ratio(totals['standard_minutes'], totals['standard_run_minutes'])
        total_qty = totals['good_qty'] + totals['defect_qty']
        quality = _ratio(totals['good_qty'], total_qty)
        oee = None
        if None not in (availability, performance, quality):
            oee = availability * performance * quality / 10000
        return {
            **totals,
            'availability': availability,
            'performance': performance,
            'quality': quality,
            'oee': oee,
            'achievement': _ratio(totals['output_qty'], totals['planned_qty']),
            'defect_rate': _ratio(totals['defect_qty'], total_qty),
        }

    @api.model
    def get_dashboard_data(self, date_from, date_to):
        measures = ['planned_qty', 'output_qty', 'good_qty', 'defect_qty', 'work_minutes', 'run_minutes',
                    'downtime_minutes', 'standard_minutes', 'standard_run_minutes']
        groups = self._read_group(
            [('date', '>=', date_from), ('date', '<=', date_to)],
            ['workcenter_id'],
            [f'{measure}:sum' for measure in measures],
            order='workcenter_id',
        )
        overall = dict.fromkeys(measures, 0.0)
        lines = []
        for workcenter, *values in groups:
            totals = dict(zip(measures, values))
            for measure, value in totals.items():
                overall[measure] += value
            lines.append({
                **self._kpis_from_totals(totals),
                'workcenter_id': workcenter.id,
                'workcenter_name': workcenter.display_name,
                'oee_target': workcenter.oee_target,
            })
        return {'overall': self._kpis_from_totals(overall), 'lines': lines}
