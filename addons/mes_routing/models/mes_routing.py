from odoo import _, api, fields, models
from odoo.exceptions import UserError


class MesRouting(models.Model):
    _name = 'mes.routing'
    _description = 'MES Routing'
    _order = 'code, id'
    _check_company_auto = True

    name = fields.Char(required=True)
    code = fields.Char(required=True, copy=False)
    active = fields.Boolean(default=True)
    company_id = fields.Many2one('res.company', required=True, default=lambda self: self.env.company)
    product_tmpl_id = fields.Many2one('product.template', string='Product', check_company=True)
    bom_id = fields.Many2one(
        'mrp.bom', string='Target BoM', check_company=True,
        domain="[('product_tmpl_id', '=', product_tmpl_id)]",
        help="Bill of Materials that receives these steps as operations.")
    step_ids = fields.One2many('mes.routing.step', 'routing_id', string='Steps', copy=True)
    total_setup_minutes = fields.Float(compute='_compute_totals')
    total_cycle_minutes = fields.Float(compute='_compute_totals', string='Total Cycle Minutes per Unit')
    note = fields.Text()

    _code_uniq = models.Constraint('unique(code, company_id)', 'Routing code must be unique per company.')

    @api.depends('step_ids.setup_minutes', 'step_ids.cycle_minutes')
    def _compute_totals(self):
        for routing in self:
            routing.total_setup_minutes = sum(routing.step_ids.mapped('setup_minutes'))
            routing.total_cycle_minutes = sum(routing.step_ids.mapped('cycle_minutes'))

    def copy_data(self, default=None):
        vals_list = super().copy_data(default=default)
        for routing, vals in zip(self, vals_list):
            vals.setdefault('code', _('%s (copy)', routing.code))
        return vals_list

    def minutes_for_qty(self, qty, workcenter=None):
        """Standard minutes to make ``qty``, optionally for one work center only."""
        self.ensure_one()
        steps = self.step_ids
        if workcenter:
            steps = steps.filtered(lambda step: step.workcenter_id == workcenter)
        return sum(step.setup_minutes + step.cycle_minutes * qty for step in steps)

    def action_apply_to_bom(self):
        """Replace the target BoM's operations with this routing's steps.

        Existing operations are archived, not deleted, so past work orders keep their link.
        ``mrp`` has no per-operation setup time, so only the cycle time is copied.
        """
        self.ensure_one()
        if not self.bom_id:
            raise UserError(_("Set a target BoM first."))
        if not self.step_ids:
            raise UserError(_("This routing has no steps."))
        self.bom_id.operation_ids.write({'active': False})
        self.env['mrp.routing.workcenter'].create([{
            'name': step.name,
            'bom_id': self.bom_id.id,
            'workcenter_id': step.workcenter_id.id,
            'sequence': step.sequence,
            'time_mode': 'manual',
            'time_cycle_manual': step.cycle_minutes,
        } for step in self.step_ids])
        return True


class MesRoutingStep(models.Model):
    _name = 'mes.routing.step'
    _description = 'MES Routing Step'
    _order = 'routing_id, sequence, id'
    _check_company_auto = True

    routing_id = fields.Many2one('mes.routing', required=True, ondelete='cascade', index=True)
    company_id = fields.Many2one(related='routing_id.company_id', store=True)
    sequence = fields.Integer(default=10)
    name = fields.Char(string='Step', required=True)
    workcenter_id = fields.Many2one('mrp.workcenter', string='Line', required=True, check_company=True)
    setup_minutes = fields.Float(help="Fixed minutes per batch.")
    cycle_minutes = fields.Float(help="Standard minutes per unit.")
    is_last_step = fields.Boolean(compute='_compute_is_last_step', store=True)

    _setup_positive = models.Constraint('CHECK(setup_minutes >= 0)', 'Setup minutes cannot be negative.')
    _cycle_positive = models.Constraint('CHECK(cycle_minutes >= 0)', 'Cycle minutes cannot be negative.')

    @api.depends('routing_id.step_ids', 'routing_id.step_ids.sequence')
    def _compute_is_last_step(self):
        for step in self:
            step.is_last_step = step == step.routing_id.step_ids.sorted()[-1:]
