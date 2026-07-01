/** @odoo-module **/

import { Component, useState, useRef, onPatched, markup } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { rpc } from "@web/core/network/rpc"; 

export class ChatDashboard extends Component {
    setup() {
        this.chatHistoryRef = useRef("chatHistory");
        this.sessionId = `session_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;

        // State reaktif OWL
        this.state = useState({
            inputQuestion: "",
            messages: [
                {
                    id: 1,
                    sender: "TEXTILE AI",
                    text: "Halo! Saya adalah asisten AI SOP Pabrik. Ada masalah atau instruksi kerja divisi Anda yang ingin ditanyakan?",
                    isUser: false,
                    time: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
                }
            ],
            isLoading: false
        });

        onPatched(() => {
            const el = this.chatHistoryRef.el;
            if (el) {
                el.scrollTop = el.scrollHeight;
            }
        });
    }

    async sendMessage() {
        const question = this.state.inputQuestion.trim();
        if (!question || this.state.isLoading) return;

        const timestamp = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
        this.state.messages.push({
            id: Date.now(),
            sender: "Operator",
            text: question,
            isUser: true,
            time: timestamp
        });

        this.state.inputQuestion = "";
        this.state.isLoading = true;

        try {
            const response = await rpc("/textile_ai/ask", { 
                question: question,
                session_id: this.sessionId
            });
            
            if (response && response.status === 'error') {
                this.state.messages.push({
                    id: Date.now() + 1,
                    sender: "Sistem Error (Backend)",
                    text: markup(response.answer), 
                    isUser: false,
                    time: timestamp
                });
            } else {
                this.state.messages.push({
                    id: Date.now() + 2,
                    sender: "TEXTILE AI",
                    text: markup(response.answer), 
                    isUser: false,
                    time: timestamp
                });
            }
        } catch (error) {
            this.state.messages.push({
                id: Date.now() + 3,
                sender: "Sistem Error (Network)",
                // 🌟 ADJUSTMENT 2: Bungkus teks error statis dengan markup() jika mengandung tag HTML agar ter-render sempurna
                text: markup(`<b>Gagal terhubung ke Server.</b> Detail: ${error.message || error}`),
                isUser: false,
                time: timestamp
            });
        } finally {
            this.state.isLoading = false;
        }
    }

    _onKeyDown(ev) {
        if (ev.key === "Enter") {
            ev.preventDefault();
            this.sendMessage();
        }
    }
}

ChatDashboard.template = "textile_rag.ChatDashboard";
registry.category("actions").add("textile_chat_dashboard_action", ChatDashboard);