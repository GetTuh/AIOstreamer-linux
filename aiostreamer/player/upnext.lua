local overlay = mp.create_osd_overlay("ass-events")
overlay.res_x = 1920
overlay.res_y = 1080

local state = { visible = false, series = "", title = "", remaining = 0, autoplay = false, accent = "&HE9AE3D&",
                loading = false, switched = false, dots = 0 }
local timer = nil
local LOADING_TIMEOUT = 60
local PLAY_KEYS = { "ENTER", "KP_ENTER" }
local BACK_KEYS = { "ESC", "GO_BACK", "MBTN_BACK", "BS" }

local function escape(text)
    local out = (text or ""):gsub("\\", "\\\226\129\160"):gsub("{", "\\{"):gsub("}", "\\}"):gsub("\n", " ")
    return out
end

local function shorten(text, limit)
    local chars = {}
    for char in (text or ""):gmatch("[%z\1-\127\194-\244][\128-\191]*") do
        chars[#chars + 1] = char
    end
    if #chars <= limit then
        return text or ""
    end
    return table.concat(chars, "", 1, limit - 1) .. "…"
end

local function ass_color(hex)
    if not hex or not hex:match("^%x%x%x%x%x%x$") then
        return nil
    end
    return "&H" .. hex:sub(5, 6) .. hex:sub(3, 4) .. hex:sub(1, 2) .. "&"
end

local function render()
    mp.set_property("user-data/aios/upnext", state.loading and "loading" or (state.visible and "shown" or ""))
    if not state.visible then
        overlay:remove()
        return
    end
    local w, h, right, bottom = 760, 230, 72, 150
    local x, y = 1920 - right - w, 1080 - bottom - h
    local box = string.format(
        "{\\an7\\pos(%d,%d)\\bord0\\shad0\\1c&H291F1A&\\1a&H08&\\p1}m 0 0 l %d 0 %d %d 0 %d{\\p0}",
        x, y, w, w, h, h)
    local accent = string.format("{\\an7\\pos(%d,%d)\\bord0\\shad0\\1c%s\\p1}m 0 0 l 8 0 8 %d 0 %d{\\p0}", x, y, state.accent, h, h)
    local head = string.format("{\\an7\\pos(%d,%d)\\fs30\\b1\\bord0\\shad0\\1c%s}%s", x + 40, y + 28, state.accent,
        state.loading and "LOADING" or "UP NEXT")
    local series = string.format("{\\an7\\pos(%d,%d)\\fs34\\bord0\\shad0\\1c&HBAABA3&}%s", x + 40, y + 70, escape(shorten(state.series, 40)))
    local title = string.format("{\\an7\\pos(%d,%d)\\fs42\\b1\\bord0\\shad0\\1c&HF9F5F3&\\q2}%s", x + 40, y + 110, escape(shorten(state.title, 44)))
    local hint
    if state.loading then
        hint = "Loading next episode" .. string.rep(".", state.dots + 1)
    elseif state.autoplay then
        hint = string.format("Playing in %ds  ·  OK play now  ·  Back dismiss", state.remaining)
    else
        hint = "OK play now  ·  Back dismiss"
    end
    local foot = string.format("{\\an7\\pos(%d,%d)\\fs28\\bord0\\shad0\\1c&HBAABA3&}%s", x + 40, y + 176, hint)
    overlay.data = table.concat({ box, accent, head, series, title, foot }, "\n")
    overlay:update()
end

local function unbind()
    for _, key in ipairs(PLAY_KEYS) do mp.remove_key_binding("aios-upnext-play-" .. key) end
    for _, key in ipairs(BACK_KEYS) do mp.remove_key_binding("aios-upnext-back-" .. key) end
end

local function hide()
    state.visible = false
    state.loading = false
    state.switched = false
    if timer then
        timer:kill()
        timer = nil
    end
    unbind()
    render()
end

local function play()
    hide()
    state.visible = true
    state.loading = true
    state.dots = 0
    local started = mp.get_time()
    timer = mp.add_periodic_timer(0.5, function()
        if mp.get_time() - started > LOADING_TIMEOUT then
            hide()
            return
        end
        state.dots = (state.dots + 1) % 3
        render()
    end)
    render()
    mp.commandv("script-message", "aios-upnext-play")
end

local function dismiss()
    hide()
    mp.commandv("script-message", "aios-upnext-dismiss")
end

local function show(series, title, seconds, autoplay, accent)
    hide()
    state.visible = true
    state.series = series
    state.title = title
    state.remaining = tonumber(seconds) or 10
    state.autoplay = autoplay == "yes"
    state.accent = ass_color(accent) or state.accent
    for _, key in ipairs(PLAY_KEYS) do mp.add_forced_key_binding(key, "aios-upnext-play-" .. key, play) end
    for _, key in ipairs(BACK_KEYS) do mp.add_forced_key_binding(key, "aios-upnext-back-" .. key, dismiss) end
    if state.autoplay then
        timer = mp.add_periodic_timer(1, function()
            if mp.get_property_bool("pause") then return end
            state.remaining = state.remaining - 1
            if state.remaining <= 0 then
                play()
            else
                render()
            end
        end)
    end
    render()
end

mp.register_script_message("aios-upnext-show", show)
mp.register_script_message("aios-upnext-hide", hide)
mp.register_event("end-file", function()
    if state.loading then
        state.switched = true
    else
        hide()
    end
end)
mp.register_event("playback-restart", function()
    if state.loading and state.switched then
        hide()
    end
end)
