# -*- coding: utf-8 -*-
import requests
import logging
from odoo import models, fields, api, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

class MrpProduction(models.Model):
    _inherit = 'mrp.production'

    ai_question = fields.Text(string='Pertanyaan ke Pakar AI')
    ai_answer = fields.Html(string='Rekomendasi SOP (Pakar AI)', readonly=True)
    ai_vector_distance = fields.Float(string='Jarak Vektor AI', readonly=True)

    def action_ask_ai_expert(self):
        """Menghubungkan Odoo dengan Endpoint FastAPI RAG Lokal"""
        self.ensure_one()
        
        if not self.ai_question or not self.ai_question.strip():
            raise UserError(_("Silakan isi kolom pertanyaan terlebih dahulu sebelum bertanya pada Pakar AI!"))

        # URL Endpoint FastAPI Anda (Sesuaikan port jika berbeda di Mac)
        api_url = "http://host.docker.internal:8000/api/query"
        payload = {
            "question": self.ai_question
        }

        try:
            # Lakukan HTTP POST Request ke FastAPI lokal
            response = requests.post(api_url, json=payload, timeout=30)
            
            if response.status_code == 200:
                result = response.json()
                
                # Update field Odoo dengan respons sukses dari Qwen + Chroma
                self.write({
                    'ai_answer': result.get('ai_answer'),
                    'ai_vector_distance': result.get('vector_distance')
                })
            else:
                error_detail = response.json().get('detail', 'Unknown Error')
                raise UserError(_("FastAPI Server merespons dengan error: %s") % error_detail)

        except requests.exceptions.ConnectionError:
            _logger.error("Gagal terhubung ke FastAPI di alamat: %s", api_url)
            raise UserError(_("Tidak dapat terhubung ke Server AI Lokal. Pastikan server FastAPI (Uvicorn) Anda sudah dinyalakan di Mac!"))
        except Exception as e:
            _logger.error("Terjadi kegagalan sistem integrasi AI: %s", str(e))
            raise UserError(_("Terjadi kesalahan internal: %s") % str(e))