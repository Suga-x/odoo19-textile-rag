import requests
import base64
from odoo import models, fields, api, _
from odoo.exceptions import UserError

class MrpSopKnowledge(models.Model):
    _name = 'mrp.sop.knowledge'
    _description = 'Basis Pengetahuan SOP Pabrik'
    _rec_name = 'sop_code'

    sop_code = fields.Char(string='Nomor/Kode SOP', required=True)
    name = fields.Char(string='Nama Prosedur', required=True)
    division = fields.Selection([
        ('dyeing', 'Divisi Dyeing / Celup'),
        ('finishing', 'Divisi Finishing / Oven'),
        ('gudang', 'Gudang / QC')
    ], string='Divisi', required=True)
    
    # field binary untuk menampung file di Odoo
    sop_file = fields.Binary(string='File Dokumen (TXT)', required=True)
    file_name = fields.Char(string='Nama File')
    state = fields.Selection([
        ('draft', 'Draft'),
        ('synced', 'Tersinkronisasi ke AI')
    ], string='Status', default='draft', readonly=True)

    def action_sync_to_ai(self):
        self.ensure_one()
        if not self.sop_file:
            raise UserError(_("Silakan unggah dokumen terlebih dahulu!"))

        # Decode data binary Odoo menjadi bytes mentah
        file_bytes = base64.b64decode(self.sop_file)
        
        # Siapkan payload Form-Data untuk FastAPI
        url = "http://host.docker.internal:8000/api/ingest"
        payload = {
            'sop_code': self.sop_code,
            'division': self.division
        }
        files = [
            ('file', (self.file_name or 'sop.txt', file_bytes, 'text/plain'))
        ]

        try:
            response = requests.post(url, data=payload, files=files, timeout=30)
            if response.status_code == 201:
                self.write({'state': 'synced'})
            else:
                raise UserError(_("FastAPI gagal memproses: %s") % response.text)
        except Exception as e:
            raise UserError(_("Gagal terhubung ke API: %s") % str(e))