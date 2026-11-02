from odoo import api, fields, models


class MesProductionPlan(models.Model):
    _inherit = 'mes.production.plan'

    result_ids = fields.One2many('mes.production.result', 'plan_id', string='Results')
    good_qty = fields.Float(compute='_compute_result_totals', store=True, string='Output Qty')
    defect_qty = fields.Float(compute='_compute_result_totals', store=True, string='Defect Qty')
    achievement_percent = fields.Float(compute='_compute_result_totals', store=True, string='Achieved %', aggregator=None)

    @api.depends('qty', 'result_ids.state', 'result_ids.output_qty', 'result_ids.defect_qty')
    def _compute_result_totals(self):
        for plan in self:
            confirmed = plan.result_ids.filtered(lambda result: result.state == 'done')
            plan.good_qty = sum(confirmed.mapped('output_qty'))
            plan.defect_qty = sum(confirmed.mapped('defect_qty'))
            plan.achievement_percent = plan.good_qty / plan.qty * 100 if plan.qty else 0

    def _sync_state_with_results(self):
        for plan in self:
            if plan.state == 'confirmed' and plan.good_qty >= plan.qty:
                plan.state = 'done'
            elif plan.state == 'done' and plan.good_qty < plan.qty:
                plan.state = 'confirmed'

    def action_open_results(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': self.name,
            'res_model': 'mes.production.result',
            'view_mode': 'list,form,pivot,graph',
            'domain': [('plan_id', '=', self.id)],
            'context': {'default_plan_id': self.id},
        }
