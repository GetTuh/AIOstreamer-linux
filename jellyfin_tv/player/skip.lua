local utils = require "mp.utils"

local overlay = mp.create_osd_overlay("ass-events")
overlay.res_x = 1920
overlay.res_y = 1080

local LABELS = { Intro = "Skip intro", Recap = "Skip recap", Preview = "Skip preview", Commercial = "Skip ad" }
local CHAPTER_PATTERNS = {
    { "^intro", "Intro" }, { "opening", "Intro" }, { "^op$", "Intro" }, { "^op[%s%d]", "Intro" },
    { "recap", "Recap" }, { "previously", "Recap" }, { "preview", "Preview" },
}
local KEYS = { "ENTER", "KP_ENTER" }
local BACK_KEYS = { "ESC", "GO_BACK", "MBTN_BACK", "BS" }

local mode = mp.get_opt("jftv-skip") or "ask"
local accent = mp.get_opt("jftv-accent") or "3daee9"
local server_segments = {}
local segments = {}
local current = nil
local handled = {}

local function ass_color(hex)
    if not hex or not hex:match("^%x%x%x%x%x%x$") then
        return "&HE9AE3D&"
    end
    return "&H" .. hex:sub(5, 6) .. hex:sub(3, 4) .. hex:sub(1, 2) .. "&"
end

local function chapter_segments()
    local list = {}
    local chapters = mp.get_property_native("chapter-list") or {}
    local duration = mp.get_property_number("duration") or 0
    for i, chapter in ipairs(chapters) do
        local title = (chapter.title or ""):lower()
        for _, pattern in ipairs(CHAPTER_PATTERNS) do
            if title:match(pattern[1]) then
                local next_chapter = chapters[i + 1]
                local finish = next_chapter and next_chapter.time or duration
                if finish > chapter.time then
                    list[#list + 1] = { kind = pattern[2], start = chapter.time, ["end"] = finish }
                end
                break
            end
        end
    end
    return list
end

local function rebuild()
    segments = {}
    for _, segment in ipairs(server_segments) do
        if LABELS[segment.kind] then
            segments[#segments + 1] = segment
        end
    end
    if #segments == 0 then
        segments = chapter_segments()
    end
end

local function unbind()
    for _, key in ipairs(KEYS) do mp.remove_key_binding("jftv-skip-" .. key) end
    for _, key in ipairs(BACK_KEYS) do mp.remove_key_binding("jftv-skip-back-" .. key) end
end

local function hide()
    if current then
        current = nil
        unbind()
        overlay:remove()
    end
end

local function skip(segment)
    handled[segment] = true
    hide()
    mp.commandv("seek", tostring(segment["end"]), "absolute")
end

local function render(segment)
    local label = LABELS[segment.kind] or "Skip"
    local w, h, right, bottom = 360, 84, 72, 150
    local x, y = 1920 - right - w, 1080 - bottom - h
    local box = string.format("{\\an7\\pos(%d,%d)\\bord0\\shad0\\1c&HF9F5F3&\\1a&H00&\\p1}m 0 0 l %d 0 %d %d 0 %d{\\p0}", x, y, w, w, h, h)
    local bar = string.format("{\\an7\\pos(%d,%d)\\bord0\\shad0\\1c%s\\p1}m 0 0 l 8 0 8 %d 0 %d{\\p0}", x, y, ass_color(accent), h, h)
    local text = string.format("{\\an4\\pos(%d,%d)\\fs40\\b1\\bord0\\shad0\\1c&H18120F&}%s", x + 36, y + h / 2, label)
    local hint = string.format("{\\an6\\pos(%d,%d)\\fs26\\bord0\\shad0\\1c&H6E6660&}OK", x + w - 28, y + h / 2)
    overlay.data = table.concat({ box, bar, text, hint }, "\n")
    overlay:update()
end

local function show(segment)
    current = segment
    for _, key in ipairs(KEYS) do
        mp.add_forced_key_binding(key, "jftv-skip-" .. key, function() skip(segment) end)
    end
    for _, key in ipairs(BACK_KEYS) do
        mp.add_forced_key_binding(key, "jftv-skip-back-" .. key, function()
            handled[segment] = true
            hide()
        end)
    end
    render(segment)
end

local function check(_, position)
    if mode == "off" or not position then
        return
    end
    local inside = nil
    for _, segment in ipairs(segments) do
        if position >= segment.start and position < segment["end"] - 1 then
            inside = segment
            break
        end
    end
    if inside ~= current then
        hide()
    end
    if not inside or handled[inside] then
        return
    end
    if mode == "auto" then
        skip(inside)
        mp.osd_message(LABELS[inside.kind] and (LABELS[inside.kind]:gsub("^Skip", "Skipped")) or "Skipped", 2)
    elseif inside ~= current then
        show(inside)
    end
end

mp.register_script_message("jftv-segments", function(json)
    server_segments = utils.parse_json(json) or {}
    rebuild()
end)

mp.register_event("file-loaded", function()
    server_segments = {}
    handled = {}
    hide()
    rebuild()
end)

mp.register_event("end-file", hide)
mp.observe_property("chapter-list", "native", rebuild)
mp.observe_property("time-pos", "number", check)
