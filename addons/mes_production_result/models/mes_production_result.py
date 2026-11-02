from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError


class MesProductionResult(models.Model):
    _name = 'mes.production.result'
    _description = 'MES Production Result'
    _order = 'date desc, id desc'
    _check_company_auto = True

    name = fields.Char(string='Reference', required=True, copy=False, readonly=True, default=lambda self: _('New'))
    company_id = fields.Many2one('res.company', required=True, default=lambda self: self.env.company)
    state = fields.Selection([('draft', 'Draft'), ('done', 'Confirmed')], default='draft', required=True, copy=False)
    date = fields.Date(
        string='Production Date', required=True, default=fields.Date.context_today, index=True,
        help="The day the output counts towards. A night shift may end on the next calendar day.")
    shift = fields.Selection([('day', 'Day'), ('swing', 'Swing'), ('night', 'Night')], default='day', required=True)
    plan_id = fields.Many2one('mes.production.plan', string='Plan', check_company=True, index=True, domain="[('state', '=', 'confirmed')]")
    routing_id = fields.Many2one(related='plan_id.routing_id')
    step_id = fields.Many2one('mes.routing.step', string='Step', check_company=True, domain="[('routing_id', '=', routing_id)]")
    workcenter_id = fields.Many2one(
        'mrp.workcenter', string='Line', required=True, check_company=True, index=True,
        compute='_compute_workcenter_id', store=True, readonly=False, precompute=True)
    product_id = fields.Many2one(
        'product.product', string='Product', required=True, check_company=True,
        compute='_compute_product_id', store=True, readonly=False, precompute=True)
    user_id = fields.Many2one('res.users', string='Operator', default=lambda self: self.env.user)
    good_qty = fields.Float(string='Good Qty')
    defect_qty = fields.Float(string='Defect Qty')
    total_qty = fields.Float(compute='_compute_quantities', store=True)
    defect_rate = fields.Float(compute='_compute_defect_rate', string='Defect %', aggregator=None)
    output_qty = fields.Float(
        compute='_compute_quantities', store=True,
        help="Good quantity that counts as finished output. Only the routing's last step counts, "
             "so a unit passing through several steps is not counted several times.")
    date_start = fields.Datetime(string='Start', required=True)
    date_end = fields.Datetime(string='End', required=True)
    downtime_minutes = fields.Float(string='Downtime (min)')
    work_minutes = fields.Float(compute='_compute_minutes', store=True, string='Elapsed (min)')
    run_minutes = fields.Float(compute='_compute_minutes', store=True, string='Run (min)')
    standard_minutes = fields.Float(
        compute='_compute_minutes', store=True, string='Standard (min)',
        help="Step cycle time × total quantity. Zero when no step is set.")
    note = fields.Text()

    _good_positive = models.Constraint('CHECK(good_qty >= 0)', 'Good quantity cannot be negative.')
    _defect_positive = models.Constraint('CHECK(defect_qty >= 0)', 'Defect quantity cannot be negative.')
    _downtime_positive = models.Constraint('CHECK(downtime_minutes >= 0)', 'Downtime cannot be negative.')

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                vals['name'] = self.env['ir.sequence'].next_by_code('mes.production.result') or _('New')
        return super().create(vals_list)

    @api.depends('step_id', 'plan_id')
    def _compute_workcenter_id(self):
        for result in self:
            result.workcenter_id = result.step_id.workcenter_id or result.plan_id.workcenter_id or result.workcenter_id

    @api.depends('plan_id')
    def _compute_product_id(self):
        for result in self:
            result.product_id = result.plan_id.product_id or result.product_id

    @api.depends('good_qty', 'defect_qty', 'step_id', 'step_id.is_last_step')
    def _compute_quantities(self):
        for result in self:
            result.total_qty = result.good_qty + result.defect_qty
            result.output_qty = result.good_qty if not result.step_id or result.step_id.is_last_step else 0

    @api.depends('total_qty', 'defect_qty')
    def _compute_defect_rate(self):
        for result in self:
            result.defect_rate = result.defect_qty / result.total_qty * 100 if result.total_qty else 0

    @api.depends('date_start', 'date_end', 'downtime_minutes', 'total_qty', 'step_id.cycle_minutes')
    def _compute_minutes(self):
        for result in self:
            elapsed = 0
            if result.date_start and result.date_end:
                elapsed = (result.date_end - result.date_start).total_seconds() / 60
            result.work_minutes = elapsed
            result.run_minutes = elapsed - result.downtime_minutes
            result.standard_minutes = result.step_id.cycle_minutes * result.total_qty

    @api.constrains('date_start', 'date_end', 'downtime_minutes')
    def _check_times(self):
        for result in self:
            if result.date_end < result.date_start:
                raise ValidationError(_("End time cannot be before start time."))
            if result.run_minutes < 0:
                raise ValidationError(_("Downtime cannot be longer than the elapsed time."))

    @api.ondelete(at_uninstall=False)
    def _unlink_except_done(self):
        if any(result.state == 'done' for result in self):
            raise UserError(_("Reset a confirmed result to draft before deleting it."))

    def action_confirm(self):
        for result in self:
            if result.plan_id and result.plan_id.state not in ('confirmed', 'done'):
                raise UserError(_("Plan %s is not confirmed.", result.plan_id.name))
            if not result.total_qty:
                raise UserError(_("Enter a good or defect quantity before confirming."))
        self.state = 'done'
        self.plan_id._sync_state_with_results()

    def action_draft(self):
        self.state = 'draft'
        self.plan_id._sync_state_with_results()
