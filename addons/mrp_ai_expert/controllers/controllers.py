# -*- coding: utf-8 -*-
import json
import requests
from odoo import http
from odoo.http import request

class TextileAiController(http.Controller):

    def _get_fastapi_url(self):
        """Mengambil URL FastAPI dari konfigurasi Odoo System Parameters"""
        ICP = request.env['ir.config_parameter'].sudo()
        # Default menggunakan IP gateway Docker yang sudah kita uji kemarin
        return ICP.get_param('textile_rag.fastapi_url', 'http://172.21.192.1:8000')

    @http.route('/textile_ai/ask', type='json', auth='public', methods=['POST'], csrf=False)
    def ask_rag_engine(self, question, **kwargs):
        """Endpoint Odoo yang akan ditembak oleh Javascript/Widget Chat Odoo"""
        if not question:
            return {'status': 'error', 'answer': 'Pertanyaan tidak boleh kosong.'}

        # Ambil divisi dari user yang sedang login di Odoo untuk otomatisasi filter RAG
        # === PROTEKSI PEMBACAAN DIVISI (SAFE-GUARD) ===
        division_name = 'Dyeing' # Set default awal pabrik
        
        try:
            # Cek apakah user yang login valid dan bukan public user
            if current_user and current_user._name == 'res.users' and current_user.id != request.env.ref('base.public_user').id:
                # Odoo memiliki variasi field tergantung versi, kita cek dengan hasattr agar anti-error
                if hasattr(current_user, 'employee_id') and current_user.employee_id:
                    division_name = current_user.employee_id.department_id.name or 'Dyeing'
                elif hasattr(current_user, 'employee') and current_user.employee:
                    division_name = current_user.employee.department_id.name or 'Dyeing'
                else:
                    # Alternatif ketiga: cari langsung ke model hr.employee jika field relasi res.users kosong
                    employee = request.env['hr.employee'].sudo().search([('user_id', '=', current_user.id)], limit=1)
                    if employee and employee.department_id:
                        division_name = employee.department_id
        except:

            pass  # Jika ada error dalam pengambilan data divisi, pakai default

        fastapi_base_url = self._get_fastapi_url()
        api_url = f"{fastapi_base_url}/api/query"

        payload = {
            "question": question,
            "division": division_name
        }
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json"
        }

        try:
            # Tembak API FastAPI dengan batas timeout 20 detik (aman dari pemblokiran karena background task)
            response = requests.post(api_url, json=payload, headers=headers, timeout=80)
            
            if response.status_code == 200:
                res_data = response.json()
                # res_data['answer'] sudah berupa HTML bersih siap render dari FastAPI!
                return {
                    'status': res_data.get('status', 'success'),
                    'answer': res_data.get('answer'),
                    'chunks': res_data.get('chunks_used', 0)
                }
            else:
                return {
                    'status': 'error',
                    'answer': f'<b>Sistem Bermasalah:</b> Gateway AI merespons dengan kode {response.status_code}.'
                }

        except requests.exceptions.Timeout:
            return {
                'status': 'timeout',
                'answer': '<b>Sistem Timeout:</b> Server AI membutuhkan waktu terlalu lama untuk menjawab. Mohon coba lagi.'
            }
        except Exception as e:
            return {
                'status': 'error',
                'answer': f'<b>Gagal Menghubungi AI:</b> Pastikan container backend aktif. Respon: {str(e)}'
            }