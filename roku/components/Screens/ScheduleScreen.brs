' Only 5 fields are shown per job (per explicit scope decision): job number,
' customer, description, operation name, and current work center. Single-line
' rows with generous column widths -- an earlier 11-column layout truncated
' badly on real hardware (Roku's system fonts render much larger than this
' was designed around). Column x offsets within a 1920-wide screen:
sub init()
    m.COLS = [
        { x: 40,   w: 180, key: "job" }
        { x: 240,  w: 320, key: "customer" }
        { x: 580,  w: 850, key: "description" }
        { x: 1450, w: 150, key: "oper" }
        { x: 1620, w: 260, key: "currwc" }
    ]

    ' Department colors come from shop-schedule's dept_colors.json (fetched by
    ' ScheduleTask alongside schedule.json), not a hardcoded table -- a shop's
    ' actual department names aren't known ahead of time and are configurable
    ' per shop via options.html. See colorsForDept(). Empty until the first
    ' successful fetch; colorsForDept()'s neutral fallback covers that gap.
    m.deptColors = {}

    m.titleLabel = m.top.findNode("titleLabel")
    m.metaLabel = m.top.findNode("metaLabel")
    m.clockLabel = m.top.findNode("clockLabel")
    m.stickyHeader = m.top.findNode("stickyHeader")
    m.stickyHeaderBg = m.top.findNode("stickyHeaderBg")
    m.stickyAccent = m.top.findNode("stickyAccent")
    m.stickyWcLabel = m.top.findNode("stickyWcLabel")
    m.stickyDeptLabel = m.top.findNode("stickyDeptLabel")
    m.stickyBacklogLabel = m.top.findNode("stickyBacklogLabel")
    m.viewport = m.top.findNode("viewport")
    m.scrollContent = m.top.findNode("scrollContent")
    m.errorBanner = m.top.findNode("errorBanner")
    m.errorLabel = m.top.findNode("errorLabel")
    m.loadingLabel = m.top.findNode("loadingLabel")
    m.scheduleTask = m.top.findNode("scheduleTask")
    m.refreshTimer = m.top.findNode("refreshTimer")
    m.scrollTimer = m.top.findNode("scrollTimer")
    m.pauseTimer = m.top.findNode("pauseTimer")
    m.clockTimer = m.top.findNode("clockTimer")
    m.manualPauseTimer = m.top.findNode("manualPauseTimer")
    m.ghostVideo = m.top.findNode("ghostVideo")
    m.ghostVideo.observeField("state", "onGhostVideoState")
    m.warpMenu = m.top.findNode("warpMenu")
    m.warpMenuList = m.top.findNode("warpMenuList")
    m.warpMenuOpenAnim = m.top.findNode("warpMenuOpenAnim")
    m.warpMenuCloseAnim = m.top.findNode("warpMenuCloseAnim")
    m.warpMenuCloseAnim.observeField("state", "onWarpMenuCloseAnimState")

    m.scheduleTask.observeField("scheduleData", "onScheduleData")
    m.refreshTimer.observeField("fire", "onRefreshTimer")
    m.scrollTimer.observeField("fire", "onScrollTick")
    m.pauseTimer.observeField("fire", "onPauseTimerFire")
    m.clockTimer.observeField("fire", "onClockTick")
    m.manualPauseTimer.observeField("fire", "onManualPauseTimerFire")

    m.viewportHeight = 1080 - 186
    m.contentHeight = 0
    m.scrollY = 0
    m.scrollState = "idle"
    m.SCROLL_SPEED = 1.1
    m.HEADER_HEIGHT = 56
    m.ROW_HEIGHT = 60
    m.sectionBounds = []
    m.currentSectionIdx = -1
    m.stickyHeader.visible = false
    m.warpMenuOpen = false
    m.warpMenuIdx = 0
    m.WARP_ROW_HEIGHT = 48
    m.WARP_VISIBLE_ROWS = 21
    ' Uniform green cells, contrasting-blue selection -- matches the web
    ' kiosk's existing work-center sidebar (options.html), not per-department
    ' colors like the rest of this screen. Blue reuses the app's existing
    ' accent color (job numbers, clock) rather than inventing a new one.
    m.WARP_ROW_COLOR = "0x2E7D32FF"
    m.WARP_ROW_SELECTED_COLOR = "0x4AAFFFFF"
end sub

sub screenShown()
    m.top.setFocus(true)
    updateClock()
    m.clockTimer.control = "start"
    startGhostVideo()

    sec = CreateObject("roRegistrySection", "ScheduleConfig")
    m.serverUrl = sec.Read("serverUrl")

    requestFetch()
    m.refreshTimer.control = "start"
end sub

' See the ghostVideo node's comment in the XML. Content is a real bundled
' video file (media/ghost.mp4) -- Video nodes need actual content to play,
' even invisible/off-screen ones; there's no "fake playing" state.
sub startGhostVideo()
    content = CreateObject("roSGNode", "ContentNode")
    content.url = "pkg:/media/ghost.mp4"
    content.streamFormat = "mp4"
    m.ghostVideo.content = content
    m.ghostVideo.control = "play"
end sub

' Safety net -- restarts ghostVideo if it ever stops or errors out instead of
' looping forever on its own (loop="true" normally handles looping natively;
' this only fires on a genuine stop/error). See the ghostVideo XML comment
' for how this was diagnosed and confirmed fixed via telnet.
sub onGhostVideoState()
    st = m.ghostVideo.state
    if st = "error" then
        print "[GHOST] errorCode="; m.ghostVideo.errorCode; " errorMsg="; m.ghostVideo.errorMsg
    end if
    if st = "finished" or st = "stopped" then
        startGhostVideo()
    end if
end sub

sub requestFetch()
    m.scheduleTask.serverUrl = m.serverUrl
    m.scheduleTask.control = "RUN"
end sub

sub onRefreshTimer()
    try
        requestFetch()
    catch e
        print "onRefreshTimer error: "; e.getMessage()
    end try
end sub

sub onClockTick()
    updateClock()
end sub

' This is the single best "is the render thread still alive" signal on
' screen -- it ticks every second independent of scrolling. If it's frozen
' too, the whole thread is dead, not just the scroll state machine.
sub updateClock()
    try
        dt = CreateObject("roDateTime")
        dt.ToLocalTime()
        h = dt.GetHours()
        ampm = "AM"
        if h = 0 then
            h = 12
        else if h = 12 then
            ampm = "PM"
        else if h > 12 then
            h = h - 12
            ampm = "PM"
        end if
        m.clockLabel.text = h.ToStr() + ":" + leftPad(dt.GetMinutes().ToStr(), 2) + ":" + leftPad(dt.GetSeconds().ToStr(), 2) + " " + ampm
    catch e
        print "updateClock error: "; e.getMessage()
    end try
end sub

function leftPad(s as String, width as Integer) as String
    result = s
    while result.Len() < width
        result = "0" + result
    end while
    return result
end function

sub onScheduleData()
    try
        ' Independent of scheduleData below -- ScheduleTask fetches both every
        ' run, so this stays current even on a cycle where schedule.json
        ' itself fails (deptColors keeps its last good value either way,
        ' see ScheduleTask.xml's field comment).
        if m.scheduleTask.deptColors <> invalid then m.deptColors = m.scheduleTask.deptColors

        data = m.scheduleTask.scheduleData
        m.loadingLabel.visible = false
        if data = invalid then
            suffix = " Showing last known schedule."
            if m.contentHeight = 0 then suffix = " No schedule loaded yet."
            m.errorLabel.text = "Connection problem: " + m.scheduleTask.errorMessage + suffix
            m.errorBanner.visible = true
            ' Leave whatever's already on screen alone -- a transient fetch failure
            ' shouldn't blank an otherwise-fine kiosk display.
            return
        end if

        m.errorBanner.visible = false

        reportDate = ""
        thruDate = ""
        if data.report_date <> invalid then reportDate = data.report_date
        if data.thru_date <> invalid then thruDate = data.thru_date
        m.metaLabel.text = "Report: " + reportDate + "   |   Thru: " + thruDate

        buildContent(data.sections)
    catch e
        print "onScheduleData error: "; e.getMessage()
    end try
end sub

' Each section's header bar is rendered inline, at its real scrolled position.
' The real content with real-world data runs to hundreds of jobs -- a full
' scroll-through at this speed takes several minutes, far longer than the
' 60s refresh interval. Resetting scrollY to 0 on every refresh (the first
' version) meant the display could never get more than a minute into the
' list before being yanked back to the top -- confirmed on real hardware as
' "restarts instead of showing the whole list." Fix: preserve scroll
' position across a refresh; only reset to 0 on the very first load.
sub buildContent(sections as Object)
    ' Guards the kiosk against ever freezing on an unexpected data shape --
    ' a crash here previously took the whole render thread down with it,
    ' leaving the last frame stuck on screen with no timers left running.
    ' See CODING_NOTES.md "Resilience" for the incident this came from.
    try
        ' A 60s refresh landing while the warp menu is open would otherwise
        ' leave it showing rows built from the section list that's about to
        ' be replaced below -- simplest fix is just closing it; m.scrollState
        ' is untouched by openWarpMenu() (only its timers stop), so the
        ' normal wasManuallyPaused handling right below still does the right
        ' thing with whatever state scrolling was actually in before it opened.
        if m.warpMenuOpen then
            m.warpMenuOpen = false
            m.warpMenu.visible = false
        end if

        previousScrollY = m.scrollY
        wasManuallyPaused = (m.scrollState = "manualPaused")

        m.scrollContent.removeChildren(m.scrollContent.getChildren(-1, 0))
        m.scrollTimer.control = "stop"
        m.pauseTimer.control = "stop"
        m.scrollState = "idle"
        m.sectionBounds = []
        m.currentSectionIdx = -1

        y = 0
        for each section in sections
            if section.jobs <> invalid and section.jobs.Count() > 0 then
                m.sectionBounds.push({ startY: y, section: section })

                headerGroup = buildSectionHeader(section, y)
                m.scrollContent.appendChild(headerGroup)
                y = y + m.HEADER_HEIGHT

                for each job in section.jobs
                    rowGroup = buildJobRow(job, y)
                    m.scrollContent.appendChild(rowGroup)
                    y = y + m.ROW_HEIGHT
                end for
            end if
        end for

        m.contentHeight = y
        maxScroll = m.contentHeight - m.viewportHeight

        if maxScroll > 0 then
            m.scrollY = previousScrollY
            if m.scrollY > maxScroll then m.scrollY = maxScroll
            if m.scrollY < 0 then m.scrollY = 0
            applyScroll()
            if wasManuallyPaused then
                m.scrollState = "manualPaused"
                m.manualPauseTimer.control = "start"
            else
                m.scrollState = "scrolling"
                m.scrollTimer.control = "start"
            end if
        else
            m.scrollY = 0
            m.scrollContent.translation = [0, 0]
            updateStickyHeader(0)
        end if
    catch e
        print "buildContent error: "; e.getMessage()
        m.errorLabel.text = "Display error building schedule -- will retry next refresh."
        m.errorBanner.visible = true
    end try
end sub

function buildSectionHeader(section as Object, y as Integer) as Object
    colors = colorsForDept(section.department)

    group = CreateObject("roSGNode", "Group")
    group.translation = [0, y]

    bg = CreateObject("roSGNode", "Rectangle")
    bg.width = 1920
    bg.height = m.HEADER_HEIGHT
    bg.color = colors.bg
    group.appendChild(bg)

    accentBar = CreateObject("roSGNode", "Rectangle")
    accentBar.width = 6
    accentBar.height = m.HEADER_HEIGHT
    accentBar.color = colors.accent
    group.appendChild(accentBar)

    wcLabel = CreateObject("roSGNode", "Label")
    wcLabel.text = section.wc
    wcLabel.translation = [30, 14]
    wcLabel.font = "font:LargeBoldSystemFont"
    wcLabel.color = "0xFFFFFFFF"
    group.appendChild(wcLabel)

    deptLabel = CreateObject("roSGNode", "Label")
    deptLabel.text = section.department + "   -   " + section.wc_group
    deptLabel.translation = [360, 20]
    deptLabel.font = "font:SmallSystemFont"
    deptLabel.color = "0x999999FF"
    group.appendChild(deptLabel)

    backlogLabel = CreateObject("roSGNode", "Label")
    backlogLabel.text = workCenterBacklogText(section)
    backlogLabel.font = "font:SmallSystemFont"
    backlogLabel.color = "0x4AAFFFFF"
    positionAfter(deptLabel, backlogLabel, 30, 20)
    group.appendChild(backlogLabel)

    return group
end function

' Positions targetLabel right after refLabel's actual rendered text width,
' not a fixed offset -- department/work-center-group names vary per shop,
' and a fixed x collided with "Assembly shop - ASSEMBLY", confirmed on real
' hardware via screenshot (one of the *shorter* real combinations, not an
' edge case). Falls back to refLabel's own position (no gap) if
' boundingRect() ever comes back invalid, rather than crashing.
sub positionAfter(refLabel as Object, targetLabel as Object, gap as Integer, y as Integer)
    refWidth = 0
    rect = refLabel.boundingRect()
    if rect <> invalid and rect.width <> invalid then refWidth = rect.width
    targetLabel.translation = [refLabel.translation[0] + refWidth + gap, y]
end sub

' "2 wk 3 day backlog" (or "open now" if nothing's queued), plus the gap size
' when there's an actual bounded opening right after that point -- matches
' update_schedule.py's generate_html() wording and the same reasoning:
' backlog alone says *when* there's room, not *how much*, and a 1-week hole can't
' take a 2-week job. backlog_days/gap_days come from schedule.json -- missing
' (invalid) on data from a shop-schedule version that predates this field,
' not just a theoretical case.
' A genuinely missing section.backlog_days (field absent entirely -- an
' older shop-schedule server that predates this field, not a reported
' zero) must NOT read as "open now". Confirmed this exact gap in practice,
' not just in theory: a server running stale code made every work center
' show "open now" during testing, even though real backlogs existed,
' simply because schedule.json didn't have the field yet. CodeRabbit catch
' on PR #7 after that happened.
function workCenterBacklogText(section as Object) as String
    if section.backlog_days = invalid then return ""

    backlogDays = section.backlog_days
    if backlogDays > 0 then
        text = fmtWeeksDays(backlogDays) + " backlog"
    else
        text = "open now"
    end if

    if section.gap_days <> invalid then
        text = text + " (" + fmtWeeksDays(section.gap_days) + " gap)"
    end if
    return text
end function

' "2 wk 3 day" style formatting from a raw day count -- omits a zero
' component ("3 day" or "2 wk", not "0 wk 3 day"). Matches
' update_schedule.py's _format_weeks_days() -- schedule.json sends integer
' days (backlog_days/gap_days), not fractional weeks, so this doesn't need
' a float-precision workaround the way decimal-weeks formatting would.
function fmtWeeksDays(daysIn as Dynamic) as String
    days = Int(daysIn)
    weeks = days \ 7
    remDays = days Mod 7
    if weeks > 0 and remDays > 0 then
        return weeks.ToStr() + " wk " + remDays.ToStr() + " day"
    else if weeks > 0 then
        return weeks.ToStr() + " wk"
    else
        return remDays.ToStr() + " day"
    end if
end function

' Always visible once there's at least one section -- deliberately simple.
' Two earlier versions tried to time the overlay's visibility against exactly
' when the real inline header should be clipped away (hidden until scrollY
' passed startY, then hidden until startY+HEADER_HEIGHT) and each attempt
' produced a real, hardware-confirmed bug: a doubled/overlapping header, then
' a "blacks out" gap during the handoff. Always-on, idx-driven only, costs a
' brief harmless moment of the overlay and the real header both showing the
' *same* matching text during each transition -- far less objectionable than
' either previous failure mode, and there's no timing window left to get
' wrong. See CODING_NOTES.md "Sticky header v2".
sub updateStickyHeader(idx as Integer)
    if idx < 0 or idx >= m.sectionBounds.Count() then return
    if idx = m.currentSectionIdx then return
    m.currentSectionIdx = idx

    section = m.sectionBounds[idx].section
    colors = colorsForDept(section.department)
    m.stickyHeader.visible = true
    m.stickyHeaderBg.color = colors.bg
    m.stickyAccent.color = colors.accent
    m.stickyWcLabel.text = section.wc
    m.stickyDeptLabel.text = section.department + "   -   " + section.wc_group
    m.stickyBacklogLabel.text = workCenterBacklogText(section)
    positionAfter(m.stickyDeptLabel, m.stickyBacklogLabel, 30, 20)
end sub

' Looks up this department's colors from dept_colors.json (see m.deptColors
' in init()) -- an exact lowercase-name match, same keying shop-schedule
' itself uses, not the substring/keyword matching this replaced. Falls back
' to a neutral gray for any department not yet in that file (e.g. before
' the first successful fetch, or a genuinely new department shop-schedule
' itself hasn't persisted a color for yet either).
function colorsForDept(department as String) as Object
    entry = m.deptColors[LCase(department)]
    if entry <> invalid and isHexColor(entry.bg) and isHexColor(entry.accent) then
        return { bg: toRokuColor(entry.bg), accent: toRokuColor(entry.accent) }
    end if
    return { bg: "0x1A1A1AFF", accent: "0x666666FF" }
end function

' Re-validated here, not just trusted from the server -- same principle as
' shop-schedule's own CODING_NOTES.md Security section ("validate hex color
' strings... again at render time"), applied on this side of the fetch too.
function isHexColor(s as Dynamic) as Boolean
    if type(s) <> "String" then return false
    return Len(s) = 7 and Left(s, 1) = "#"
end function

' "#rrggbb" (dept_colors.json) -> "0xRRGGBBFF" (Roku SceneGraph color field,
' full opacity).
function toRokuColor(hexColor as String) as String
    return "0x" + Mid(hexColor, 2) + "FF"
end function

' Work-center warp menu (OK key) -- lets a full scroll-through (several
' minutes with real production data) be skipped by jumping straight to a
' section. Built fresh from m.sectionBounds every time it opens rather than
' kept live while hidden -- it's only ever on screen momentarily, and
' sections only change on a data refresh anyway.
sub openWarpMenu()
    try
        if m.sectionBounds.Count() = 0 then return

        m.scrollTimer.control = "stop"
        m.pauseTimer.control = "stop"
        m.manualPauseTimer.control = "stop"

        m.warpMenuList.removeChildren(m.warpMenuList.getChildren(-1, 0))
        ' Direct node references, not re-found by id later -- see
        ' highlightWarpMenuRow()'s comment for why this replaced an earlier
        ' findNode("bg")-per-row version that silently never highlighted
        ' anything on real hardware.
        m.warpMenuRowBgs = []
        for i = 0 to m.sectionBounds.Count() - 1
            rowInfo = buildWarpMenuRow(m.sectionBounds[i].section, i)
            m.warpMenuList.appendChild(rowInfo.group)
            m.warpMenuRowBgs.push(rowInfo.bg)
        end for
        m.warpMenuList.translation = [0, 0]

        m.warpMenuIdx = m.currentSectionIdx
        if m.warpMenuIdx < 0 then m.warpMenuIdx = 0
        m.warpMenuOpen = true
        ' Reset off-screen before showing/animating -- guards against a
        ' prior close animation having been interrupted mid-slide (e.g. by
        ' buildContent()'s force-close) and leaving translation.x partway in.
        m.warpMenu.translation = [-320, 0]
        m.warpMenu.visible = true
        m.warpMenuOpenAnim.control = "start"
        highlightWarpMenuRow()
    catch e
        print "openWarpMenu error: "; e.getMessage()
        m.warpMenuOpen = false
        m.warpMenu.visible = false
    end try
end sub

' Uniform green cell, work-center name only -- matches the web kiosk's
' existing sidebar filter (options.html), not this screen's own per-
' department section-header styling. See highlightWarpMenuRow() for the
' selected-state color swap.
' Returns { group, bg } -- the caller keeps bg directly in m.warpMenuRowBgs
' rather than re-finding it by id later (see openWarpMenu()).
function buildWarpMenuRow(section as Object, idx as Integer) as Object
    group = CreateObject("roSGNode", "Group")
    group.translation = [10, idx * m.WARP_ROW_HEIGHT]

    bg = CreateObject("roSGNode", "Rectangle")
    bg.width = 300
    bg.height = m.WARP_ROW_HEIGHT - 4
    bg.color = m.WARP_ROW_COLOR
    group.appendChild(bg)

    wcLabel = CreateObject("roSGNode", "Label")
    wcLabel.text = section.wc
    wcLabel.translation = [14, 11]
    wcLabel.font = "font:SmallBoldSystemFont"
    wcLabel.color = "0xFFFFFFFF"
    group.appendChild(wcLabel)

    return { group: group, bg: bg }
end function

' Snaps (not animates -- this is discrete keyboard selection, not the
' panel's own slide) the highlighted row's background and keeps it inside
' warpMenuViewport's clipped window by shifting warpMenuList's translation.
' Earlier version re-found each row's background via row.findNode("bg")
' every call instead of keeping the reference from buildWarpMenuRow() --
' confirmed on real hardware that nothing ever actually highlighted, with
' no error printed either. Kept the direct-reference array instead of
' digging further into why findNode didn't surface the row here, since it
' removes the indirection entirely rather than explaining one specific
' failure of it.
sub highlightWarpMenuRow()
    try
        for i = 0 to m.warpMenuRowBgs.Count() - 1
            if i = m.warpMenuIdx then
                m.warpMenuRowBgs[i].color = m.WARP_ROW_SELECTED_COLOR
            else
                m.warpMenuRowBgs[i].color = m.WARP_ROW_COLOR
            end if
        end for

        targetTop = m.warpMenuIdx * m.WARP_ROW_HEIGHT
        targetBottom = targetTop + m.WARP_ROW_HEIGHT
        viewTop = -m.warpMenuList.translation[1]
        viewBottom = viewTop + (m.WARP_VISIBLE_ROWS * m.WARP_ROW_HEIGHT)
        if targetTop < viewTop then
            m.warpMenuList.translation = [0, -targetTop]
        else if targetBottom > viewBottom then
            m.warpMenuList.translation = [0, -(targetBottom - (m.WARP_VISIBLE_ROWS * m.WARP_ROW_HEIGHT))]
        end if
    catch e
        print "highlightWarpMenuRow error: "; e.getMessage()
    end try
end sub

' Visibility turns off in onWarpMenuCloseAnimState() once the slide-out
' animation actually finishes, not here -- hiding immediately would skip
' straight past it instead of sliding out.
sub closeWarpMenu()
    try
        m.warpMenuOpen = false
        m.warpMenuCloseAnim.control = "start"

        ' Resume auto-scroll the same way manualScroll() does -- paused, then
        ' auto-resumes a few seconds after the last input, rather than snapping
        ' straight back into motion right as the menu closes.
        maxScroll = m.contentHeight - m.viewportHeight
        if maxScroll > 0 then
            m.scrollState = "manualPaused"
            m.manualPauseTimer.control = "stop"
            m.manualPauseTimer.control = "start"
        end if
    catch e
        print "closeWarpMenu error: "; e.getMessage()
        m.warpMenuOpen = false
        m.warpMenu.visible = false
        m.scrollState = "idle"
    end try
end sub

sub onWarpMenuCloseAnimState()
    if m.warpMenuCloseAnim.state = "stopped" then
        m.warpMenu.visible = false
    end if
end sub

sub warpToSelection()
    try
        target = m.sectionBounds[m.warpMenuIdx]
        maxScroll = m.contentHeight - m.viewportHeight

        m.scrollY = target.startY
        if m.scrollY > maxScroll then m.scrollY = maxScroll
        if m.scrollY < 0 then m.scrollY = 0
        applyScroll()
    catch e
        print "warpToSelection error: "; e.getMessage()
    end try
    closeWarpMenu()
end sub

function buildJobRow(job as Object, y as Integer) as Object
    group = CreateObject("roSGNode", "Group")
    group.translation = [0, y]

    bg = CreateObject("roSGNode", "Rectangle")
    bg.width = 1920
    bg.height = m.ROW_HEIGHT
    bg.color = "0x0A0A14FF"
    group.appendChild(bg)

    addCell(group, colByKey("job"),         job.job,         "0x4AAFFFFF", "font:MediumBoldSystemFont")
    addCell(group, colByKey("customer"),    job.customer,    "0xCCCCCCFF", "font:MediumSystemFont")
    addCell(group, colByKey("description"), job.description, "0x999999FF", "font:MediumSystemFont")
    addCell(group, colByKey("oper"),        job.oper,        "0xCCCCCCFF", "font:MediumSystemFont")
    addCell(group, colByKey("currwc"),      job.curr_wc,     "0xFFFFFFFF", "font:MediumBoldSystemFont")

    return group
end function

function colByKey(key as String) as Object
    for each col in m.COLS
        if col.key = key then return col
    end for
    return { x: 0, w: 100 }
end function

sub addCell(parent as Object, col as Object, text as String, color as String, font as String)
    label = CreateObject("roSGNode", "Label")
    if text = invalid then text = ""
    label.text = text
    label.translation = [col.x, 16]
    label.width = col.w
    label.font = font
    label.color = color
    parent.appendChild(label)
end sub

' Scroll loop: scroll down, pause at the bottom, snap to top, pause there,
' repeat. Not a seamless infinite-wrap like the web kiosk's doubled-content
' trick -- a visible reset is a reasonable tradeoff for how much simpler it
' is to get right in SceneGraph, and still reads fine as "auto-scrolling".
' This fires ~33x/second for as long as the kiosk is scrolling -- any
' uncaught error here previously killed the whole render thread (nothing
' left to fire the clock, refresh timer, or anything else), leaving the
' last frame frozen on screen permanently. On error: stop the scroll timer
' (so it doesn't re-throw every tick) and let the next successful refresh's
' buildContent() restart scrolling cleanly, rather than crash the channel.
sub onScrollTick()
    try
        maxScroll = m.contentHeight - m.viewportHeight
        if maxScroll <= 0 then return

        m.scrollY = m.scrollY + m.SCROLL_SPEED
        if m.scrollY >= maxScroll then
            m.scrollY = maxScroll
            applyScroll()
            m.scrollState = "pausedAtBottom"
            m.scrollTimer.control = "stop"
            m.pauseTimer.duration = 3
            m.pauseTimer.control = "start"
        else
            applyScroll()
        end if
    catch e
        print "onScrollTick error: "; e.getMessage()
        m.scrollTimer.control = "stop"
        m.scrollState = "idle"
    end try
end sub

sub applyScroll()
    m.scrollContent.translation = [0, -m.scrollY]

    ' Find which section the viewport's top edge currently sits within, and
    ' swap the sticky header the moment that section starts, same as the web
    ' kiosk's CSS position:sticky section headers.
    idx = 0
    for i = 0 to m.sectionBounds.Count() - 1
        if m.sectionBounds[i].startY <= m.scrollY then
            idx = i
        else
            exit for
        end if
    end for
    updateStickyHeader(idx)
end sub

sub onPauseTimerFire()
    try
        if m.scrollState = "pausedAtBottom" then
            m.scrollY = 0
            applyScroll()
            m.scrollState = "pausedAtTop"
            m.pauseTimer.duration = 2
            m.pauseTimer.control = "start"
        else if m.scrollState = "pausedAtTop" then
            m.scrollState = "scrolling"
            m.scrollTimer.control = "start"
        end if
    catch e
        print "onPauseTimerFire error: "; e.getMessage()
        m.scrollState = "idle"
    end try
end sub

' Press "options" (the asterisk/star key) to reset the configured server and
' return to setup. Deliberately not a commonly-pressed key -- this runs
' unattended on a shop floor TV and shouldn't be easy to trigger by accident.
' Up/Down scroll manually; auto-scroll pauses while in manual control and
' resumes a few seconds after the last press, same idea as the web kiosk
' pausing on wheel/touch input. OK opens the work-center warp menu and
' (once open) selects the highlighted row -- same button, context-dependent,
' matching SetupScreen.brs's existing OK-does-different-things-by-focus
' pattern rather than introducing a new one. Chosen over an earlier Left-to-
' open version that tested as unintuitive -- OK is the one button every
' remote user already reaches for to "do the thing."
function onKeyEvent(key as String, press as Boolean) as Boolean
    if not press then return false

    if m.warpMenuOpen then
        ' Swallow every key while the menu is open (the trailing `return true`
        ' below) so Up/Down can't also drive the main schedule's manualScroll
        ' underneath it, and "options" can't reset setup mid-menu.
        if key = "up" then
            if m.warpMenuIdx > 0 then
                m.warpMenuIdx = m.warpMenuIdx - 1
                highlightWarpMenuRow()
            end if
        else if key = "down" then
            if m.warpMenuIdx < m.sectionBounds.Count() - 1 then
                m.warpMenuIdx = m.warpMenuIdx + 1
                highlightWarpMenuRow()
            end if
        else if key = "OK" then
            warpToSelection()
        else if key = "back" then
            closeWarpMenu()
        end if
        return true
    end if

    if key = "options" then
        m.top.reconfigure = true
        return true
    else if key = "up" then
        manualScroll(-200)
        return true
    else if key = "down" then
        manualScroll(200)
        return true
    else if key = "OK" then
        openWarpMenu()
        return true
    end if
    return false
end function

sub manualScroll(delta as Integer)
    try
        maxScroll = m.contentHeight - m.viewportHeight
        if maxScroll <= 0 then return

        m.scrollTimer.control = "stop"
        m.pauseTimer.control = "stop"
        m.scrollState = "manualPaused"

        m.scrollY = m.scrollY + delta
        if m.scrollY < 0 then m.scrollY = 0
        if m.scrollY > maxScroll then m.scrollY = maxScroll
        applyScroll()

        m.manualPauseTimer.control = "stop"
        m.manualPauseTimer.control = "start"
    catch e
        print "manualScroll error: "; e.getMessage()
        m.scrollState = "idle"
    end try
end sub

sub onManualPauseTimerFire()
    try
        if m.scrollState <> "manualPaused" then return
        m.scrollState = "scrolling"
        m.scrollTimer.control = "start"
    catch e
        print "onManualPauseTimerFire error: "; e.getMessage()
        m.scrollState = "idle"
    end try
end sub
