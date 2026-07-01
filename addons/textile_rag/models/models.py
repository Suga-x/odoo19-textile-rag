# from odoo import models, fields, api


# class textile_rag(models.Model):
#     _name = 'textile_rag.textile_rag'
#     _description = 'textile_rag.textile_rag'

#     name = fields.Char()
#     value = fields.Integer()
#     value2 = fields.Float(compute="_value_pc", store=True)
#     description = fields.Text()
#
#     @api.depends('value')
#     def _value_pc(self):
#         for record in self:
#             record.value2 = float(record.value) / 100

