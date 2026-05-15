use eframe::egui::{self, CentralPanel, Color32, Frame, Margin, ScrollArea, SidePanel, TextEdit, TopBottomPanel, Vec2};
use serde::{Deserialize, Serialize};
use std::cell::RefCell;
use std::rc::Rc;
use wasm_bindgen::closure::Closure;
use wasm_bindgen::JsCast;

// ── Data types ─────────────────────────────────────────────────────────

#[derive(Clone, Serialize, Deserialize)]
struct TerminalInfo {
    id: String,
    #[serde(default)]
    alive: bool,
}

#[derive(Clone, Serialize, Deserialize)]
struct StatusResp {
    id: String,
    #[serde(default)]
    alive: bool,
    #[serde(default)]
    pid: Option<u32>,
    #[serde(default)]
    cwd: Option<String>,
    #[serde(default)]
    created_at: Option<String>,
    #[serde(default)]
    last_activity: Option<String>,
    #[serde(default)]
    reader_error: Option<String>,
}

#[derive(Clone, Deserialize)]
struct WsMsg {
    #[serde(rename = "type")]
    msg_type: String,
    text: Option<String>,
    cursor: Option<i64>,
    timestamp: Option<String>,
    events: Option<Vec<HistoryEvent>>,
    status: Option<StatusResp>,
}

#[derive(Clone, Deserialize)]
struct HistoryEvent {
    #[serde(rename = "type")]
    event_type: String,
    text: Option<String>,
    timestamp: Option<String>,
}

#[derive(Clone, Serialize)]
struct WsSend {
    #[serde(rename = "type")]
    msg_type: String,
    text: Option<String>,
    rows: Option<u16>,
    cols: Option<u16>,
}

// ── App state ──────────────────────────────────────────────────────────

struct AppState {
    terminals: Vec<TerminalInfo>,
    selected_id: Option<String>,
    output_lines: Vec<String>,
    input_text: String,
    error: Option<String>,
    loading: bool,
    ws_connected: bool,
    show_new_dialog: bool,
    new_name: String,
    terminal_status: Option<StatusResp>,
}

impl AppState {
    fn new() -> Self {
        Self {
            terminals: vec![],
            selected_id: None,
            output_lines: vec![],
            input_text: String::new(),
            error: None,
            loading: false,
            ws_connected: false,
            show_new_dialog: false,
            new_name: String::new(),
            terminal_status: None,
        }
    }
}

enum AppAction {
    SetTerminals(Vec<TerminalInfo>),
    AddOutput(String),
    SetHistory(Vec<String>),
    SetStatus(StatusResp),
    SetError(String),
    SetWsConnected(bool),
    SetLoading(bool),
    RemoveTerminal(String),
}

// ── TerminalApp ────────────────────────────────────────────────────────

struct TerminalApp {
    state: Rc<RefCell<AppState>>,
    ws: RefCell<Option<web_sys::WebSocket>>,
}

impl TerminalApp {
    fn new() -> Self {
        Self {
            state: Rc::new(RefCell::new(AppState::new())),
            ws: RefCell::new(None),
        }
    }

    fn apply(&self, action: AppAction) {
        let mut s = self.state.borrow_mut();
        match action {
            AppAction::SetTerminals(t) => {
                s.terminals = t;
                s.loading = false;
            }
            AppAction::AddOutput(text) => {
                for line in text.split('\n') {
                    s.output_lines.push(line.to_string());
                }
                if s.output_lines.len() > 10000 {
                    s.output_lines.drain(0..5000);
                }
            }
            AppAction::SetHistory(lines) => {
                s.output_lines = lines;
            }
            AppAction::SetStatus(st) => {
                s.terminal_status = Some(st);
            }
            AppAction::SetError(e) => {
                s.error = Some(e);
                s.loading = false;
            }
            AppAction::SetWsConnected(v) => s.ws_connected = v,
            AppAction::SetLoading(v) => s.loading = v,
            AppAction::RemoveTerminal(id) => {
                s.terminals.retain(|t| t.id != id);
                if s.selected_id.as_deref() == Some(&id) {
                    s.selected_id = None;
                    s.output_lines.clear();
                    s.terminal_status = None;
                    s.ws_connected = false;
                }
            }
        }
    }

    fn host_url() -> String {
        let loc = web_sys::window().unwrap().location();
        format!("{}//{}", loc.protocol().unwrap(), loc.host().unwrap())
    }

    fn ws_protocol() -> &'static str {
        let loc = web_sys::window().unwrap().location();
        if loc.protocol().unwrap_or_default() == "https:" {
            "wss:"
        } else {
            "ws:"
        }
    }

    fn fetch_terminals(state: Rc<RefCell<AppState>>) {
        wasm_bindgen_futures::spawn_local(async move {
            Self::apply_inner(&state, AppAction::SetLoading(true));
            let url = format!("{}/api/terminals", Self::host_url());
            match gloo_net::http::Request::get(&url).send().await {
                Ok(resp) => match resp.json::<Vec<TerminalInfo>>().await {
                    Ok(list) => Self::apply_inner(&state, AppAction::SetTerminals(list)),
                    Err(e) => Self::apply_inner(&state, AppAction::SetError(e.to_string())),
                },
                Err(e) => Self::apply_inner(&state, AppAction::SetError(e.to_string())),
            }
        });
    }

    fn create_terminal(state: Rc<RefCell<AppState>>, name: &str) {
        let name = name.to_string();
        wasm_bindgen_futures::spawn_local(async move {
            let url = format!("{}/api/create", Self::host_url());
            let body = serde_json::json!({
                "name": name,
                "interactive": true,
            });
            match gloo_net::http::Request::post(&url)
                .json(&body)
                .unwrap()
                .send()
                .await
            {
                Ok(resp) => {
                    if resp.ok() {
                        Self::fetch_terminals(state.clone());
                        {
                            let mut s = state.borrow_mut();
                            s.show_new_dialog = false;
                            s.new_name.clear();
                        }
                    } else if let Ok(v) = resp.json::<serde_json::Value>().await {
                        let msg = v
                            .get("error")
                            .and_then(|e| e.as_str())
                            .unwrap_or("create failed");
                        Self::apply_inner(&state, AppAction::SetError(msg.to_string()));
                    }
                }
                Err(e) => Self::apply_inner(&state, AppAction::SetError(e.to_string())),
            }
        });
    }

    fn kill_terminal(state: Rc<RefCell<AppState>>, id: &str) {
        let id = id.to_string();
        wasm_bindgen_futures::spawn_local(async move {
            let url = format!("{}/api/kill/{id}", Self::host_url());
            let _ = gloo_net::http::Request::post(&url).send().await;
            Self::fetch_terminals(state);
        });
    }

    fn delete_terminal(state: Rc<RefCell<AppState>>, id: &str) {
        let id = id.to_string();
        wasm_bindgen_futures::spawn_local(async move {
            let url = format!("{}/api/terminals/{id}", Self::host_url());
            let _ = gloo_net::http::Request::delete(&url).send().await;
            Self::apply_inner(&state, AppAction::RemoveTerminal(id));
            Self::fetch_terminals(state.clone());
        });
    }

    fn send_input(ws: &web_sys::WebSocket, text: &str) {
        let msg = WsSend {
            msg_type: "input".to_string(),
            text: Some(text.to_string()),
            rows: None,
            cols: None,
        };
        if let Ok(json) = serde_json::to_string(&msg) {
            let _ = ws.send_with_str(&json);
        }
    }

    fn connect_ws(state: Rc<RefCell<AppState>>, terminal_id: &str) -> web_sys::WebSocket {
        let host = {
            let loc = web_sys::window().unwrap().location();
            loc.host().unwrap()
        };
        let url = format!("{}//{host}/ws/{terminal_id}", Self::ws_protocol());
        let ws = web_sys::WebSocket::new(&url).unwrap();

        let s = state.clone();
        let onopen = Closure::wrap(Box::new(move || {
            Self::apply_inner(&s, AppAction::SetWsConnected(true));
        }) as Box<dyn FnMut()>);
        ws.set_onopen(Some(onopen.as_ref().unchecked_ref()));
        onopen.forget();

        let s = state.clone();
        let onclose = Closure::wrap(Box::new(move || {
            Self::apply_inner(&s, AppAction::SetWsConnected(false));
        }) as Box<dyn FnMut()>);
        ws.set_onclose(Some(onclose.as_ref().unchecked_ref()));
        onclose.forget();

        let s = state.clone();
        let onmsg = Closure::wrap(Box::new(move |e: web_sys::MessageEvent| {
            let text = e.data().dyn_into::<js_sys::JsString>().ok().and_then(|s| s.as_string());
            if let Some(json_str) = text {
                if let Ok(msg) = serde_json::from_str::<WsMsg>(&json_str) {
                    match msg.msg_type.as_str() {
                        "history" => {
                            let lines: Vec<String> = msg
                                .events
                                .unwrap_or_default()
                                .into_iter()
                                .map(|h| h.text.unwrap_or_default())
                                .collect();
                            Self::apply_inner(&s, AppAction::SetHistory(lines));
                        }
                        "output" => {
                            if let Some(t) = msg.text {
                                Self::apply_inner(&s, AppAction::AddOutput(t));
                            }
                        }
                        "status" => {
                            if let Some(st) = msg.status {
                                Self::apply_inner(&s, AppAction::SetStatus(st));
                            }
                        }
                        _ => {}
                    }
                }
            }
        }) as Box<dyn FnMut(web_sys::MessageEvent)>);
        ws.set_onmessage(Some(onmsg.as_ref().unchecked_ref()));
        onmsg.forget();

        ws
    }

    fn apply_inner(state: &Rc<RefCell<AppState>>, action: AppAction) {
        let mut s = state.borrow_mut();
        match action {
            AppAction::SetTerminals(t) => {
                s.terminals = t;
                s.loading = false;
            }
            AppAction::AddOutput(text) => {
                for line in text.split('\n') {
                    s.output_lines.push(line.to_string());
                }
                if s.output_lines.len() > 10000 {
                    s.output_lines.drain(0..5000);
                }
            }
            AppAction::SetHistory(lines) => {
                s.output_lines = lines;
            }
            AppAction::SetStatus(st) => s.terminal_status = Some(st),
            AppAction::SetError(e) => {
                s.error = Some(e);
                s.loading = false;
            }
            AppAction::SetWsConnected(v) => s.ws_connected = v,
            AppAction::SetLoading(v) => s.loading = v,
            AppAction::RemoveTerminal(id) => {
                s.terminals.retain(|t| t.id != id);
                if s.selected_id.as_deref() == Some(&id) {
                    s.selected_id = None;
                    s.output_lines.clear();
                    s.terminal_status = None;
                    s.ws_connected = false;
                }
            }
        }
    }
}

impl eframe::App for TerminalApp {
    fn update(&mut self, ctx: &egui::Context, _frame: &mut eframe::Frame) {
        setup_style(ctx);

        // ── Top bar ────────────────────────────────────────────────────
        TopBottomPanel::top("header")
            .frame(Frame {
                fill: Color32::from_rgb(20, 18, 16),
                inner_margin: Margin::symmetric(16, 8),
                ..Default::default()
            })
            .show(ctx, |ui| {
                ui.horizontal(|ui| {
                    ui.label(
                        egui::RichText::new("i4z · terminal")
                            .color(Color32::from_rgb(200, 168, 248))
                            .heading(),
                    );
                    ui.with_layout(egui::Layout::right_to_left(egui::Align::Center), |ui| {
                        let state = self.state.borrow();
                        let status = if state.ws_connected {
                            format!("● {}", state.selected_id.as_deref().unwrap_or(""))
                        } else {
                            String::new()
                        };
                        ui.label(
                            egui::RichText::new(status)
                                .color(if state.ws_connected {
                                    Color32::from_rgb(114, 208, 138)
                                } else {
                                    Color32::from_rgb(102, 96, 90)
                                })
                                .size(12.0),
                        );
                        if let Some(err) = &state.error {
                            ui.label(
                                egui::RichText::new(format!("⚠ {err}"))
                                    .color(Color32::from_rgb(240, 120, 120))
                                    .size(12.0),
                            );
                        }
                    });
                });
            });

        // ── Sidebar ────────────────────────────────────────────────────
        SidePanel::left("sidebar")
            .resizable(false)
            .default_width(220.0)
            .frame(Frame {
                fill: Color32::from_rgb(20, 18, 16),
                inner_margin: Margin::symmetric(8, 8),
                ..Default::default()
            })
            .show(ctx, |ui| {
                ui.vertical(|ui| {
                    // New terminal button
                    if ui
                        .add(
                            egui::Button::new(
                                egui::RichText::new("＋ New Terminal")
                                    .color(Color32::from_rgb(200, 168, 248)),
                            )
                            .fill(Color32::from_rgb(28, 20, 56))
                            .min_size(Vec2::new(ui.available_width(), 32.0)),
                        )
                        .clicked()
                    {
                        self.state.borrow_mut().show_new_dialog = true;
                    }

                    ui.separator();

                    // Terminal list
                    let state = self.state.borrow();
                    let selected = state.selected_id.clone();
                    let terminals = state.terminals.clone();
                    let mut clicked_id: Option<String> = None;
                    let state_rc = self.state.clone();
                    drop(state);

                    ScrollArea::vertical()
                        .auto_shrink([false; 2])
                        .show(ui, |ui| {
                            for t in &terminals {
                                let is_selected = selected.as_deref() == Some(&t.id);
                                let label = if t.alive {
                                    format!("● {}", t.id)
                                } else {
                                    format!("○ {}", t.id)
                                };
                                let color = if t.alive {
                                    Color32::from_rgb(114, 208, 138)
                                } else {
                                    Color32::from_rgb(102, 96, 90)
                                };
                                let response = ui.add_sized(
                                    Vec2::new(ui.available_width(), 24.0),
                                    egui::SelectableLabel::new(
                                        is_selected,
                                        egui::RichText::new(&label).color(color).size(13.0),
                                    ),
                                );
                                if response.clicked() {
                                    clicked_id = Some(t.id.clone());
                                }
                                // Right-click context menu
                                let id = t.id.clone();
                                let s = state_rc.clone();
                                response.context_menu(move |ui| {
                                    if ui.button("Kill").clicked() {
                                        Self::kill_terminal(s.clone(), &id);
                                        ui.close_menu();
                                    }
                                    if ui.button("Delete").clicked() {
                                        Self::delete_terminal(s.clone(), &id);
                                        ui.close_menu();
                                    }
                                });
                            }
                        });

                    // Handle selection outside the closure (avoids drop(ui))
                    if let Some(id) = clicked_id {
                        let mut state = self.state.borrow_mut();
                        state.selected_id = Some(id.clone());
                        state.output_lines.clear();
                        state.terminal_status = None;
                        drop(state);

                        if let Some(old_ws) = self.ws.borrow_mut().take() {
                            let _ = old_ws.close();
                        }
                        let state = self.state.clone();
                        let ws = Self::connect_ws(state, &id);
                        *self.ws.borrow_mut() = Some(ws);
                    }
                });
            });

        // ── Main panel ─────────────────────────────────────────────────
        CentralPanel::default()
            .frame(Frame {
                fill: Color32::from_rgb(12, 11, 9),
                inner_margin: Margin::symmetric(12, 8),
                ..Default::default()
            })
            .show(ctx, |ui| {
                let state = self.state.borrow();
                let has_selection = state.selected_id.is_some();

                if !has_selection {
                    ui.vertical_centered(|ui| {
                        ui.add_space(100.0);
                        ui.label(
                            egui::RichText::new("Select a terminal from the sidebar")
                                .color(Color32::from_rgb(102, 96, 90))
                                .size(16.0),
                        );
                    });
                    return;
                }

                // Terminal info bar
                if let Some(st) = &state.terminal_status {
                    ui.horizontal(|ui| {
                        ui.label(
                            egui::RichText::new(state.selected_id.as_deref().unwrap_or(""))
                                .color(Color32::from_rgb(200, 168, 248))
                                .strong(),
                        );
                        if let Some(cwd) = &st.cwd {
                            ui.label(
                                egui::RichText::new(cwd)
                                    .color(Color32::from_rgb(102, 96, 90))
                                    .size(12.0),
                            );
                        }
                        ui.with_layout(egui::Layout::right_to_left(egui::Align::Center), |ui| {
                            ui.label(
                                egui::RichText::new(if state.ws_connected {
                                    "● connected"
                                } else {
                                    "○ disconnected"
                                })
                                .color(if state.ws_connected {
                                    Color32::from_rgb(114, 208, 138)
                                } else {
                                    Color32::from_rgb(240, 120, 120)
                                })
                                .size(11.0),
                            );
                        });
                    });
                    ui.separator();
                }

                // Terminal output
                let output_lines = state.output_lines.clone();
                drop(state);

                let num_lines = output_lines.len();
                ScrollArea::vertical()
                    .id_salt("terminal_output")
                    .auto_shrink([false; 2])
                    .stick_to_bottom(true)
                    .show(ui, |ui| {
                        ui.add_space(4.0);
                        for line in &output_lines {
                            ui.label(
                                egui::RichText::new(line)
                                    .monospace()
                                    .color(Color32::from_rgb(237, 232, 223))
                                    .size(13.0),
                            );
                        }
                        if num_lines == 0 {
                            ui.label(
                                egui::RichText::new("Waiting for output…")
                                    .color(Color32::from_rgb(102, 96, 90))
                                    .size(13.0),
                            );
                        }
                    });

                // Input bar
                ui.add_space(4.0);
                ui.separator();
                ui.horizontal(|ui| {
                    let mut state = self.state.borrow_mut();
                    let resp = ui.add_sized(
                        Vec2::new(ui.available_width() - 60.0, 28.0),
                        TextEdit::singleline(&mut state.input_text)
                            .hint_text("Type a command…")
                            .font(egui::TextStyle::Monospace),
                    );
                    let send_clicked = ui
                        .add(
                            egui::Button::new(
                                egui::RichText::new("Send").color(Color32::from_rgb(200, 168, 248)),
                            )
                            .fill(Color32::from_rgb(28, 20, 56))
                            .min_size(Vec2::new(50.0, 28.0)),
                        )
                        .clicked();
                    if (resp.lost_focus() && ui.input(|i| i.key_pressed(egui::Key::Enter)))
                        || send_clicked
                    {
                        let text = std::mem::take(&mut state.input_text);
                        if !text.is_empty() {
                            if let Some(ws) = self.ws.borrow().as_ref() {
                                Self::send_input(ws, &text);
                            }
                        }
                        resp.request_focus();
                    }
                    if !resp.has_focus() {
                        resp.request_focus();
                    }
                });
            });

        // ── New terminal dialog ────────────────────────────────────────
        let show = self.state.borrow().show_new_dialog;
        if show {
            let state = self.state.clone();
            egui::Window::new("New Terminal")
                .collapsible(false)
                .resizable(false)
                .anchor(egui::Align2::CENTER_CENTER, [0.0, 0.0])
                .frame(Frame {
                    fill: Color32::from_rgb(27, 25, 22),
                    inner_margin: Margin::symmetric(20, 16),
                    ..Default::default()
                })
                .show(ctx, |ui| {
                    let mut s = state.borrow_mut();
                    ui.label("Terminal name:");
                    ui.add(
                        TextEdit::singleline(&mut s.new_name)
                            .hint_text("my-terminal")
                            .font(egui::TextStyle::Monospace)
                            .min_size(Vec2::new(200.0, 24.0)),
                    );
                    ui.add_space(12.0);
                    ui.horizontal(|ui| {
                        if ui
                            .add(
                                egui::Button::new(
                                    egui::RichText::new("Cancel")
                                        .color(Color32::from_rgb(160, 148, 136)),
                                )
                                .fill(Color32::from_rgb(35, 32, 28)),
                            )
                            .clicked()
                        {
                            s.show_new_dialog = false;
                            s.new_name.clear();
                        }
                        if ui
                            .add(
                                egui::Button::new(
                                    egui::RichText::new("Create")
                                        .color(Color32::from_rgb(200, 168, 248)),
                                )
                                .fill(Color32::from_rgb(28, 20, 56)),
                            )
                            .clicked()
                        {
                            let name = s.new_name.trim().to_string();
                            if !name.is_empty() {
                                drop(s);
                                Self::create_terminal(state.clone(), &name);
                            }
                        }
                    });
                });
        }

        // Auto-refresh terminal list
        ctx.request_repaint_after(std::time::Duration::from_secs(3));
    }
}

// ── Styling ────────────────────────────────────────────────────────────

fn setup_style(ctx: &egui::Context) {
    let mut style = (*ctx.style()).clone();
    style.visuals.dark_mode = true;
    style.visuals.window_fill = Color32::from_rgb(27, 25, 22);
    style.visuals.panel_fill = Color32::from_rgb(12, 11, 9);
    style.visuals.faint_bg_color = Color32::from_rgb(20, 18, 16);
    style.visuals.widgets.noninteractive.bg_fill = Color32::from_rgb(27, 25, 22);
    style.visuals.widgets.inactive.bg_fill = Color32::from_rgb(35, 32, 28);
    style.visuals.widgets.active.bg_fill = Color32::from_rgb(43, 40, 36);
    style.visuals.widgets.hovered.bg_fill = Color32::from_rgb(51, 48, 43);
    style.visuals.selection.bg_fill = Color32::from_rgb(60, 40, 128);
    style.visuals.selection.stroke.color = Color32::from_rgb(200, 168, 248);
    style.visuals.window_stroke.color = Color32::from_rgb(46, 43, 38);
    style.visuals.hyperlink_color = Color32::from_rgb(200, 168, 248);
    style.spacing.item_spacing = Vec2::new(8.0, 4.0);
    style.spacing.button_padding = Vec2::new(6.0, 3.0);
    ctx.set_style(style);
}

// ── Entry point ────────────────────────────────────────────────────────

#[cfg(target_arch = "wasm32")]
fn main() {
    eframe::WebLogger::init(log::LevelFilter::Debug).ok();

    let web_options = eframe::WebOptions::default();

    wasm_bindgen_futures::spawn_local(async {
        let app = TerminalApp::new();
        let state = app.state.clone();
        TerminalApp::fetch_terminals(state);

        let canvas = web_sys::window()
            .and_then(|w| w.document())
            .and_then(|d| d.get_element_by_id("the_canvas_id"))
            .and_then(|e| e.dyn_into::<web_sys::HtmlCanvasElement>().ok())
            .expect("canvas #the_canvas_id not found");

        eframe::WebRunner::new()
            .start(
                canvas,
                web_options,
                Box::new(|_cc| Ok(Box::new(app))),
            )
            .await
            .expect("failed to start eframe");
    });
}
