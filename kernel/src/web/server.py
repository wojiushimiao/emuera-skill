from __future__ import annotations

import asyncio
import json
import os
import traceback
from typing import Any

from aiohttp import web, WSMsgType

from ..io.renderer import IORenderer


class WebSocketRenderer(IORenderer):

    def __init__(self) -> None:
        self._ws_clients: list[web.WebSocketResponse] = []
        self._input_futures: list[asyncio.Future] = []
        self._current_color: int = -1
        self._output_buffer: list[str] = []
        self._pending_input_future: asyncio.Future | None = None

    def add_client(self, ws: web.WebSocketResponse) -> None:
        self._ws_clients.append(ws)

    def remove_client(self, ws: web.WebSocketResponse) -> None:
        if ws in self._ws_clients:
            self._ws_clients.remove(ws)

    async def _broadcast(self, data: dict) -> None:
        payload = json.dumps(data, ensure_ascii=False)
        dead = []
        for ws in self._ws_clients:
            try:
                await ws.send_str(payload)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.remove_client(ws)

    async def handle_input_response(self, value: Any) -> None:
        if self._pending_input_future is not None and not self._pending_input_future.done():
            self._pending_input_future.set_result(value)
            self._pending_input_future = None

    def print_text(self, text: str, newline: bool = False, wait: bool = False) -> None:
        content = text + ("\n" if newline else "")
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(self._broadcast({"type": "output", "content": content}))
        except RuntimeError:
            pass

    def print_formatted(self, segments: list, newline: bool = False, wait: bool = False) -> None:
        parts: list[str] = []
        for seg in segments:
            seg_type = seg.get("type", "text")
            seg_value = seg.get("value", "")
            parts.append(str(seg_value))
        content = "".join(parts) + ("\n" if newline else "")
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(self._broadcast({"type": "output", "content": content}))
        except RuntimeError:
            pass

    def input_number(self, prompt: str = "", timeout: int = 0) -> int:
        try:
            loop = asyncio.get_running_loop()
            future = loop.create_future()
            self._pending_input_future = future
            loop.create_task(self._broadcast({
                "type": "input_required",
                "prompt": prompt,
                "input_type": "number",
            }))
            result = asyncio.get_event_loop().run_until_complete(future)
            try:
                return int(result)
            except (ValueError, TypeError):
                return 0
        except Exception:
            return 0

    def input_string(self, prompt: str = "", timeout: int = 0) -> str:
        try:
            loop = asyncio.get_running_loop()
            future = loop.create_future()
            self._pending_input_future = future
            loop.create_task(self._broadcast({
                "type": "input_required",
                "prompt": prompt,
                "input_type": "string",
            }))
            result = asyncio.get_event_loop().run_until_complete(future)
            return str(result)
        except Exception:
            return ""

    async def input_number_async(self, prompt: str = "", timeout: int = 0) -> int:
        future = asyncio.get_event_loop().create_future()
        self._pending_input_future = future
        await self._broadcast({
            "type": "input_required",
            "prompt": prompt,
            "input_type": "number",
        })
        try:
            if timeout > 0:
                result = await asyncio.wait_for(future, timeout=timeout)
            else:
                result = await future
            try:
                return int(result)
            except (ValueError, TypeError):
                return 0
        except asyncio.TimeoutError:
            return 0

    async def input_string_async(self, prompt: str = "", timeout: int = 0) -> str:
        future = asyncio.get_event_loop().create_future()
        self._pending_input_future = future
        await self._broadcast({
            "type": "input_required",
            "prompt": prompt,
            "input_type": "string",
        })
        try:
            if timeout > 0:
                result = await asyncio.wait_for(future, timeout=timeout)
            else:
                result = await future
            return str(result)
        except asyncio.TimeoutError:
            return ""

    def draw_line(self, char: str = "-") -> None:
        content = char * 80 + "\n"
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(self._broadcast({"type": "output", "content": content}))
        except RuntimeError:
            pass

    def clear_line(self, count: int = 1) -> None:
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(self._broadcast({"type": "clear", "count": count}))
        except RuntimeError:
            pass

    def set_color(self, color: int) -> None:
        self._current_color = color
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(self._broadcast({"type": "color", "color": color}))
        except RuntimeError:
            pass

    def reset_color(self) -> None:
        self._current_color = -1
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(self._broadcast({"type": "color", "color": -1}))
        except RuntimeError:
            pass

    def print_button(self, text: str, value: Any) -> None:
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(self._broadcast({
                "type": "button",
                "text": text,
                "value": value,
            }))
        except RuntimeError:
            pass

    def draw_bar(self, current: int, max_val: int, length: int, fill_char: str = "*", empty_char: str = ".") -> None:
        if max_val <= 0:
            ratio = 0.0
        else:
            ratio = current / max_val
        if ratio < 0.0:
            ratio = 0.0
        if ratio > 1.0:
            ratio = 1.0
        fill_count = int(ratio * length)
        empty_count = length - fill_count
        bar_str = fill_char * fill_count + empty_char * empty_count
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(self._broadcast({"type": "output", "content": f"[{bar_str}]\n"}))
        except RuntimeError:
            pass


class ERBWebServer:

    def __init__(self, engine, host: str = "localhost", port: int = 8080) -> None:
        self.engine = engine
        self.host = host
        self.port = port
        self._app: web.Application | None = None
        self._runner: web.AppRunner | None = None
        self._renderer: WebSocketRenderer | None = None
        self._game_task: asyncio.Task | None = None
        self._setup_routes()

    def _setup_routes(self) -> None:
        self._app = web.Application()
        self._app.router.add_get("/api/status", self._handle_status)
        self._app.router.add_get("/api/variables/{name}", self._handle_get_variable)
        self._app.router.add_post("/api/variables/{name}", self._handle_set_variable)
        self._app.router.add_get("/api/characters", self._handle_get_characters)
        self._app.router.add_get("/api/characters/{id}", self._handle_get_character)
        self._app.router.add_post("/api/input", self._handle_input)
        self._app.router.add_post("/api/command/{id}", self._handle_command)
        self._app.router.add_post("/api/save", self._handle_save)
        self._app.router.add_post("/api/load", self._handle_load)
        self._app.router.add_get("/api/functions", self._handle_get_functions)
        self._app.router.add_post("/api/llm/generate", self._handle_llm_generate)
        self._app.router.add_post("/api/llm/script", self._handle_llm_script)
        self._app.router.add_post("/api/llm/debug", self._handle_llm_debug)
        self._app.router.add_get("/ws", self._handle_websocket)
        self._app.router.add_get("/", self._handle_index)
        static_dir = os.path.join(os.path.dirname(__file__), "static")
        self._app.router.add_static("/static/", static_dir, name="static")

    async def _handle_index(self, request: web.Request) -> web.FileResponse:
        static_dir = os.path.join(os.path.dirname(__file__), "static")
        return web.FileResponse(os.path.join(static_dir, "index.html"))

    async def _handle_status(self, request: web.Request) -> web.Response:
        vm = self.engine.vm
        vmgr = self.engine.variable_mgr
        if vm is None or vmgr is None:
            return web.json_response({"error": "Engine not initialized"}, status=503)
        mode = getattr(self.engine, "_begin_mode", "UNKNOWN")
        chara_num = int(vmgr.get_value("CHARANUM", []))
        money = int(vmgr.get_value("MONEY", []))
        day = int(vmgr.get_value("DAY", []))
        time_val = int(vmgr.get_value("TIME", []))
        target = int(vmgr.get_value("TARGET", []))
        master = int(vmgr.get_value("MASTER", []))
        return web.json_response({
            "mode": mode,
            "running": self.engine._running,
            "chara_num": chara_num,
            "money": money,
            "day": day,
            "time": time_val,
            "target": target,
            "master": master,
        })

    async def _handle_get_variable(self, request: web.Request) -> web.Response:
        vmgr = self.engine.variable_mgr
        if vmgr is None:
            return web.json_response({"error": "Engine not initialized"}, status=503)
        var_name = request.match_info["name"].upper()
        try:
            desc = vmgr.get_descriptor(var_name)
            if desc is None:
                return web.json_response({"error": f"Variable '{var_name}' not found"}, status=404)
            indices_str = request.query.get("indices", "")
            indices = []
            if indices_str:
                indices = [int(x.strip()) for x in indices_str.split(",")]
            value = vmgr.get_value(var_name, indices)
            if hasattr(value, "tolist"):
                value = value.tolist()
            elif isinstance(value, dict):
                serialized = {}
                for k, v in value.items():
                    if hasattr(v, "tolist"):
                        serialized[str(k)] = v.tolist()
                    else:
                        serialized[str(k)] = v
                value = serialized
            return web.json_response({
                "name": var_name,
                "value": value,
                "type": desc.var_type,
                "dimensions": desc.dimensions,
                "is_character_var": desc.is_character_var,
                "is_readonly": desc.is_readonly,
            })
        except (KeyError, IndexError) as e:
            return web.json_response({"error": str(e)}, status=400)

    async def _handle_set_variable(self, request: web.Request) -> web.Response:
        vmgr = self.engine.variable_mgr
        if vmgr is None:
            return web.json_response({"error": "Engine not initialized"}, status=503)
        var_name = request.match_info["name"].upper()
        try:
            body = await request.json()
            value = body.get("value")
            indices = body.get("indices", [])
            desc = vmgr.get_descriptor(var_name)
            if desc is None:
                return web.json_response({"error": f"Variable '{var_name}' not found"}, status=404)
            if desc.is_readonly:
                return web.json_response({"error": f"Variable '{var_name}' is read-only"}, status=403)
            vmgr.set_value(var_name, indices, value)
            if self._renderer:
                await self._renderer._broadcast({
                    "type": "state_change",
                    "variable": var_name,
                    "value": value,
                })
            return web.json_response({"success": True, "name": var_name, "value": value})
        except (KeyError, ValueError, IndexError) as e:
            return web.json_response({"error": str(e)}, status=400)

    async def _handle_get_characters(self, request: web.Request) -> web.Response:
        vmgr = self.engine.variable_mgr
        if vmgr is None:
            return web.json_response({"error": "Engine not initialized"}, status=503)
        chara_num = int(vmgr.get_value("CHARANUM", []))
        characters = []
        for cid in range(chara_num):
            char_data = self._get_character_data(vmgr, cid)
            characters.append(char_data)
        return web.json_response({"characters": characters, "count": chara_num})

    async def _handle_get_character(self, request: web.Request) -> web.Response:
        vmgr = self.engine.variable_mgr
        if vmgr is None:
            return web.json_response({"error": "Engine not initialized"}, status=503)
        try:
            char_id = int(request.match_info["id"])
            char_data = self._get_character_data(vmgr, char_id)
            return web.json_response(char_data)
        except (KeyError, IndexError, ValueError) as e:
            return web.json_response({"error": str(e)}, status=400)

    def _get_character_data(self, vmgr, char_id: int) -> dict:
        char_vars = ["BASE", "MAXBASE", "ABL", "TALENT", "EXP", "MARK", "PALAM",
                     "CFLAG", "CSTR", "STAIN", "TEQUIP", "EQUIP", "JUEL", "NOWEX",
                     "EX", "RELATION"]
        data: dict[str, Any] = {"id": char_id}
        for var_name in char_vars:
            desc = vmgr.get_descriptor(var_name)
            if desc is None:
                continue
            try:
                value = vmgr.get_value(var_name, [char_id])
                if hasattr(value, "tolist"):
                    value = value.tolist()
                elif isinstance(value, dict):
                    continue
                if isinstance(value, list):
                    named_items = {}
                    name_map = getattr(desc, "name_map", {})
                    if name_map:
                        for idx, val in enumerate(value):
                            if idx < len(value):
                                name = None
                                for n, i in name_map.items():
                                    if i == idx:
                                        name = n
                                        break
                                if name:
                                    named_items[name] = val
                                named_items[str(idx)] = val
                        data[var_name.lower()] = named_items
                    else:
                        data[var_name.lower()] = value
            except (KeyError, IndexError):
                continue
        return data

    async def _handle_input(self, request: web.Request) -> web.Response:
        try:
            body = await request.json()
            value = body.get("value")
            if self._renderer and self._renderer._pending_input_future is not None:
                if not self._renderer._pending_input_future.done():
                    self._renderer._pending_input_future.set_result(value)
                    self._renderer._pending_input_future = None
            return web.json_response({"success": True})
        except Exception as e:
            return web.json_response({"error": str(e)}, status=400)

    async def _handle_command(self, request: web.Request) -> web.Response:
        vm = self.engine.vm
        if vm is None:
            return web.json_response({"error": "Engine not initialized"}, status=503)
        try:
            cmd_id = int(request.match_info["id"])
            vmgr = self.engine.variable_mgr
            vmgr.set_value("SELECTCOM", [], cmd_id)
            return web.json_response({"success": True, "command": cmd_id})
        except Exception as e:
            return web.json_response({"error": str(e)}, status=400)

    async def _handle_save(self, request: web.Request) -> web.Response:
        try:
            body = await request.json()
            slot = body.get("slot", 1)
            save_dir = os.path.join(self.engine.game_dir, "Sav")
            os.makedirs(save_dir, exist_ok=True)
            save_path = os.path.join(save_dir, f"save{slot:02d}.sav")
            self.engine.save_game(save_path)
            return web.json_response({"success": True, "path": save_path})
        except Exception as e:
            return web.json_response({"error": str(e)}, status=500)

    async def _handle_load(self, request: web.Request) -> web.Response:
        try:
            body = await request.json()
            slot = body.get("slot", 1)
            save_path = os.path.join(self.engine.game_dir, "Sav", f"save{slot:02d}.sav")
            if not os.path.exists(save_path):
                return web.json_response({"error": f"Save file not found: {save_path}"}, status=404)
            self.engine.load_game(save_path)
            if self._renderer:
                await self._renderer._broadcast({"type": "state_change", "variable": "LOAD", "value": slot})
            return web.json_response({"success": True, "path": save_path})
        except Exception as e:
            return web.json_response({"error": str(e)}, status=500)

    async def _handle_get_functions(self, request: web.Request) -> web.Response:
        fdispatch = self.engine.function_dispatch
        if fdispatch is None:
            return web.json_response({"error": "Engine not initialized"}, status=503)
        functions = []
        for name, desc in fdispatch._functions.items():
            functions.append({
                "name": name,
                "is_function": desc.is_function,
                "is_functions": desc.is_functions,
                "parameter_count": desc.parameter_count,
                "is_event": desc.is_event,
                "is_system": desc.is_system,
                "source_file": desc.source_file,
                "call_count": desc.call_count,
            })
        query = request.query.get("q", "").upper()
        if query:
            functions = [f for f in functions if query in f["name"]]
        return web.json_response({"functions": functions, "count": len(functions)})

    async def _handle_llm_generate(self, request: web.Request) -> web.Response:
        bridge = self.engine.llm_bridge
        if bridge is None:
            return web.json_response({"error": "LLM not configured"}, status=503)
        try:
            body = await request.json()
            event_type = body.get("event_type", "")
            target_id = body.get("target_id", 0)
            player_id = body.get("player_id", 0)
            location = body.get("location", "")
            custom_prompt = body.get("custom_prompt", "")
            from ..llm.llm_content import EventContext
            ctx = EventContext(
                target_id=target_id,
                player_id=player_id,
                current_location=location,
                custom_prompt=custom_prompt,
            )
            result = await bridge.content_generator.generate_event_text(event_type, ctx)
            return web.json_response({"result": result})
        except Exception as e:
            return web.json_response({"error": str(e)}, status=500)

    async def _handle_llm_script(self, request: web.Request) -> web.Response:
        bridge = self.engine.llm_bridge
        if bridge is None:
            return web.json_response({"error": "LLM not configured"}, status=503)
        try:
            body = await request.json()
            action = body.get("action", "generate")
            if action == "generate":
                func_name = body.get("function_name", "")
                description = body.get("description", "")
                from ..llm.llm_script import FunctionSpec
                spec = FunctionSpec(
                    function_name=func_name,
                    description=description,
                    parameters=body.get("parameters", []),
                    constraints=body.get("constraints", []),
                    output_type=body.get("output_type", ""),
                )
                result = await bridge.script_generator.generate_function(spec)
            elif action == "modify":
                source = body.get("source_code", "")
                mod_request = body.get("modification_request", "")
                result = await bridge.script_modifier.modify_function(source, mod_request)
            elif action == "fix":
                source = body.get("source_code", "")
                error_msg = body.get("error_message", "")
                result = await bridge.script_modifier.fix_bug(source, error_msg, {})
            else:
                return web.json_response({"error": f"Unknown action: {action}"}, status=400)
            return web.json_response({"result": result})
        except Exception as e:
            return web.json_response({"error": str(e)}, status=500)

    async def _handle_llm_debug(self, request: web.Request) -> web.Response:
        bridge = self.engine.llm_bridge
        if bridge is None:
            return web.json_response({"error": "LLM not configured"}, status=503)
        try:
            body = await request.json()
            action = body.get("action", "analyze")
            if action == "analyze":
                error = body.get("error", "")
                call_stack = body.get("call_stack", [])
                snapshot = body.get("variable_snapshot", {})
                result = await bridge.debug_assistant.analyze_error(error, call_stack, snapshot)
                return web.json_response({
                    "error_type": result.error_type,
                    "root_cause": result.root_cause,
                    "affected_variables": result.affected_variables,
                    "suggested_fix": result.suggested_fix,
                    "confidence": result.confidence,
                    "related_code_locations": result.related_code_locations,
                })
            elif action == "suggest":
                source = body.get("source_code", "")
                error_desc = body.get("error_description", "")
                suggestions = await bridge.debug_assistant.suggest_fix(source, error_desc)
                return web.json_response({
                    "suggestions": [
                        {"description": s.description, "code_change": s.code_change, "confidence": s.confidence}
                        for s in suggestions
                    ]
                })
            elif action == "explain":
                source = body.get("source_code", "")
                question = body.get("question", "")
                result = await bridge.debug_assistant.explain_code(source, question)
                return web.json_response({"explanation": result})
            else:
                return web.json_response({"error": f"Unknown action: {action}"}, status=400)
        except Exception as e:
            return web.json_response({"error": str(e)}, status=500)

    async def _handle_websocket(self, request: web.Request) -> web.WebSocketResponse:
        ws = web.WebSocketResponse()
        await ws.prepare(request)
        if self._renderer is None:
            self._renderer = WebSocketRenderer()
            self.engine.io_renderer = self._renderer
        self._renderer.add_client(ws)
        try:
            async for msg in ws:
                if msg.type == WSMsgType.TEXT:
                    try:
                        data = json.loads(msg.data)
                        msg_type = data.get("type", "")
                        if msg_type == "input":
                            value = data.get("value")
                            await self._renderer.handle_input_response(value)
                        elif msg_type == "ping":
                            await ws.send_str(json.dumps({"type": "pong"}))
                    except json.JSONDecodeError:
                        pass
                elif msg.type == WSMsgType.ERROR:
                    break
        finally:
            self._renderer.remove_client(ws)
        return ws

    async def start(self) -> None:
        if self._renderer is None:
            self._renderer = WebSocketRenderer()
            self.engine.io_renderer = self._renderer
        self._runner = web.AppRunner(self._app)
        await self._runner.setup()
        port = self.port
        for attempt in range(10):
            try:
                site = web.TCPSite(self._runner, self.host, port)
                await site.start()
                self._site = site
                self.port = port
                if port != (self.__dict__.get('_orig_port', port)):
                    print("Web server started on http://%s:%d (original port %d was busy)" % (self.host, port, self.__dict__.get('_orig_port', port)))
                else:
                    print("Web server started on http://%s:%d" % (self.host, port))
                print("PID: %d" % os.getpid())
                return
            except OSError as e:
                if e.errno == 10048 and attempt < 9:
                    port = self.port + attempt + 1
                    print("Port %d busy, trying port %d..." % (port - 1, port))
                else:
                    raise

    async def stop(self) -> None:
        if self._game_task is not None and not self._game_task.done():
            self._game_task.cancel()
            try:
                await self._game_task
            except asyncio.CancelledError:
                pass
        if self._runner is not None:
            await self._runner.cleanup()
