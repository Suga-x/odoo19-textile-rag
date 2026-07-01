import os
from litellm import completion
from dotenv import load_dotenv

load_dotenv()

class LLMService:
    @staticmethod
    def generate_rag_answer_history(question: str, retrieved_sop: str, history: list[dict[str, str]]) -> str:
        ai_provider = os.getenv("AI_PROVIDER", "ollama").lower()
        
        # 1. Susun instruksi kaku seperti biasa
        system_instruction = (
            "Anda adalah Pakar Manajemen Sistem Mutu di pabrik tekstil makloon celup.\n"
            "Tugas Anda adalah menjawab pertanyaan operator secara taktis, ringkas, dan mudah dipahami.\n\n"
            
            "ATURAN FORMAT OUTPUT (MUTLAK & KETAT):\n"
            "1. WAJIB menggunakan format HTML murni untuk semua dekorasi teks.\n"
            "2. Gunakan tag <b>...</b> untuk menebalkan judul, poin penting, parameter suhu, angka persen, atau kode dokumen.\n"
            "3. Gunakan tag <ul> dan <li> jika jawaban berupa urutan langkah atau daftar solusi.\n"
            "4. Gunakan tag <br/><br/> untuk memberikan jeda baris antar paragraf.\n"
            "5. DILARANG KERAS MENGGUNAKAN MARKDOWN SEPERTI ASTERIS (**Penjelasan:** atau **Teks Bold**). Ganti semua format tebal markdown menjadi tag <b>.\n"
            "6. DILARANG KERAS membungkus jawaban dengan markdown code blocks seperti ```html ... ```.\n"
            "7. Jika di dalam dokumen referensi terdapat nomor SOP atau instruksi spesifik, sebutkan secara jelas.\n\n"
            
            "DOKUMEN REFERENSI SOP:\n"
            f"{retrieved_sop}"
        )
        messages_payload = [
            {'role': 'system', 'content': system_instruction}
        ]
        
        for msg in history[-4:]:
            role = "user" if msg["role"] == "Operator" else "assistant"
            messages_payload.append({'role': role, 'content': msg["content"]})
            
        messages_payload.append({'role': 'user', 'content': f"Pertanyaan Operator: {question}"})
        try:
            if ai_provider == "gemini":
                print(" 🌐 [LLM ROUTER] Mencoba menghubungi Google Gemini API dengan konteks riwayat...")
                response = completion(
                    model="gemini/gemini-1.5-pro",
                    messages=messages_payload, # Menggunakan payload dinamis
                    temperature=0.2,
                    timeout=15 
                )
                return response.choices[0].message.content
            
        except Exception as e:
            print(f" [LLM FALLBACK] Gemini bermasalah: {str(e)}. Mengalihkan proses ke Ollama lokal...")
            
        # Pintu Darurat: Eksekusi Ollama Lokal (Qwen)
        try:
            print("[LLM ROUTER] Menjalankan Ollama Lokal (qwen2.5-coder:14b) dengan konteks riwayat...")
            response = completion(
                model="ollama/qwen2.5-coder:14b",
                messages=messages_payload, 
                temperature=0.2
            )
            return response.choices[0].message.content
            
        except Exception as local_err:
            print(f" [LLM FATAL] Ollama lokal juga gagal: {str(local_err)}")
            return (
                "<b>Sistem AI Mengalami Gangguan:</b> Hubungan ke otak AI (Gemini & Ollama) terputus. "
                "Namun berdasarkan pencarian database, dokumen SOP terkait ditemukan. Silakan hubungi tim IT pabrik."
            )

    @staticmethod
    def generate_rag_answer(question: str, retrieved_sop: str) -> str:
        ai_provider = os.getenv("AI_PROVIDER", "ollama").lower()
        
        # Susun instruksi kaku seperti biasa
        system_instruction = (
            "Anda adalah Pakar Manajemen Sistem Mutu di pabrik tekstil makloon celup.\n"
            "Tugas Anda adalah menjawab pertanyaan operator secara taktis, ringkas, dan mudah dipahami.\n\n"
            
            "ATURAN FORMAT OUTPUT (MUTLAK & KETAT):\n"
            "1. WAJIB menggunakan format HTML murni untuk semua dekorasi teks.\n"
            "2. Gunakan tag <b>...</b> untuk menebalkan judul, poin penting, parameter suhu, angka persen, atau kode dokumen.\n"
            "3. Gunakan tag <ul> dan <li> jika jawaban berupa urutan langkah atau daftar solusi.\n"
            "4. Gunakan tag <br/><br/> untuk memberikan jeda baris antar paragraf.\n"
            "5. DILARANG KERAS MENGGUNAKAN MARKDOWN SEPERTI ASTERIS (**Penjelasan:** atau **Teks Bold**). Ganti semua format tebal markdown menjadi tag <b>.\n"
            "6. DILARANG KERAS membungkus jawaban dengan markdown code blocks seperti ```html ... ```.\n"
            "7. Jika di dalam dokumen referensi terdapat nomor SOP atau instruksi spesifik, sebutkan secara jelas.\n\n"
            
            "CONTOH OUTPUT YANG BENAR:\n"
            "<b>Kemungkinan Penyebab:</b> Kain poliester mengalami kerutan.<br/><br/>\n"
            "<b>Solusi berdasarkan SOP-DYE-005:</b>\n"
            "<ul>\n"
            "  <li>Turunkan suhu menjadi <b>90°C</b> selama 30 menit.</li>\n"
            "</ul><br/>\n"
            "<b>Penjelasan:</b> Proses ini bertujuan mendistribusikan molekul warna.\n\n"
            
            "DOKUMEN REFERENSI SOP:\n"
            f"{retrieved_sop}"
        )
        
        # TARUH LOGIKA PERTAHANAN DI SINI (TRY-EXCEPT COUPLING)
        try:
            if ai_provider == "gemini":
                print(" [LLM ROUTER] Mencoba menghubungi Google Gemini API...")
                response = completion(
                    model="gemini/gemini-1.5-pro",
                    messages=[
                        {'role': 'system', 'content': system_instruction},
                        {'role': 'user', 'content': f"Pertanyaan Operator: {question}"}
                    ],
                    temperature=0.2,
                    timeout=15 # Batasi waktu tunggu maksimal 15 detik
                )
                return response.choices[0].message.content
            
        except Exception as e:
            # Jika Gemini gagal (Error 503, internet mati, atau kuota habis), JANGAN CRASH!
            # Langsung alihkan ke Ollama lokal di PC kantor secara otomatis.
            print(f" [LLM FALLBACK] Gemini bermasalah: {str(e)}. Mengalihkan proses ke Ollama lokal...")
            
        # Pintu Darurat: Eksekusi Ollama Lokal (Qwen)
        try:
            print("[LLM ROUTER] Menjalankan Ollama Lokal (qwen2.5-coder:14b)...")
            response = completion(
                model="ollama/qwen2.5-coder:14b",
                messages=[
                    {'role': 'system', 'content': system_instruction},
                    {'role': 'user', 'content': f"Pertanyaan Operator: {question}"}
                ],
                temperature=0.2
            )
            return response.choices[0].message.content
            
        except Exception as local_err:
            # Jika Ollama lokal pun mati, kembalikan teks HTML aman buatan sistem
            print(f" [LLM FATAL] Ollama lokal juga gagal: {str(local_err)}")
            return (
                "<b>Sistem AI Mengalami Gangguan:</b> Hubungan ke otak AI (Gemini & Ollama) terputus. "
                "Namun berdasarkan pencarian database, dokumen SOP terkait ditemukan. Silakan hubungi tim IT pabrik."
            )