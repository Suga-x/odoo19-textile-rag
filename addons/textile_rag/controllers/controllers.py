# -*- coding: utf-8 -*-
import requests
import logging
from odoo import http
from odoo.http import request
from odoo.tools import html_sanitize

_logger = logging.getLogger(__name__)

class TextileAiController(http.Controller):
    
    def _get_fastapi_url(self):
        ICP = request.env['ir.config_parameter'].sudo()
        return ICP.get_param('textile_rag.fastapi_url', 'http://host.docker.internal:8000')

    @http.route('/textile_ai/ask', type='json', auth='user', methods=['POST'], csrf=False)
    def ask_rag_engine(self, question, session_id=None, **kwargs):
        """
        Endpoint jembatan RPC dari Odoo OWL ke FastAPI Server.
        Menerima parameter 'session_id' agar riwayat obrolan terjaga.
        """
        if not question:
            return {'status': 'error', 'answer': 'Pertanyaan tidak boleh kosong.'}

        # Jika OWL lupa mengirim session_id, buat fallback berbasis ID User Odoo agar aman
        if not session_id:
            session_id = f"odoo_user_{request.env.uid}"

        api_url = f"{self._get_fastapi_url().strip().rstrip('/')}/api/query/history"
        
        # Masukkan session_id ke dalam payload yang dikirim ke FastAPI
        payload = {
            "question": question, 
            "session_id": session_id,
            "division": "dyeing"  # Sementara hardcode, nanti bisa dinamis dari context user
        }
        headers = {"Content-Type": "application/json", "Accept": "application/json"}

        try:
            _logger.info("Mengirim query RAG ke FastAPI untuk Session: %s", session_id)
            response = requests.post(api_url, json=payload, headers=headers, timeout=60)
            
            if response.status_code == 200:
                res_data = response.json()
                return {
                    'status': res_data.get('status', 'success'),
                    'answer': html_sanitize(res_data.get('answer', '')),
                    'chunks': res_data.get('chunks_used', 0)
                }
                
            _logger.error("FastAPI Error %s: %s", response.status_code, response.text)
            return {'status': 'error', 'answer': f'<b>Server AI Merespons Error:</b> Kode {response.status_code}'}
            
        except Exception as e:
            _logger.exception("Gagal menghubungi RAG Engine FastAPI Server")
            return {'status': 'error', 'answer': f'<b>Gagal Menghubungi AI:</b> {str(e)}'}