# from odoo import models, fields, api


# class mrp_ai_expert(models.Model):
#     _name = 'mrp_ai_expert.mrp_ai_expert'
#     _description = 'mrp_ai_expert.mrp_ai_expert'

#     name = fields.Char()
#     value = fields.Integer()
#     value2 = fields.Float(compute="_value_pc", store=True)
#     description = fields.Text()
#
#     @api.depends('value')
#     def _value_pc(self):
#         for record in self:
#             record.value2 = float(record.value) / 100

