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

    ' Set by teardown() -- checked by onGhostVideoState()/startGhostVideo()
    ' so stopping ghostVideo (and a pending ghostRetryTimer firing after)
    ' can't restart it right back up during reconfiguration.
    m.tornDown = false

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
    m.ghostRetryTimer = m.top.findNode("ghostRetryTimer")
    m.ghostVideo = m.top.findNode("ghostVideo")
    m.ghostVideo.observeField("state", "onGhostVideoState")
    m.warpMenu = m.top.findNode("warpMenu")
    m.warpMenuList = m.top.findNode("warpMenuList")
    m.warpMenuOpenAnim = m.top.findNode("warpMenuOpenAnim")
    m.warpMenuCloseAnim = m.top.findNode("warpMenuCloseAnim")
    m.warpMenuCloseAnim.observeField("state", "onWarpMenuCloseAnimState")

    m.scheduleTask.observeField("scheduleData", "onScheduleData")
    m.scheduleTask.observeField("deptColors", "onDeptColors")
    m.refreshTimer.observeField("fire", "onRefreshTimer")
    m.scrollTimer.observeField("fire", "onScrollTick")
    m.pauseTimer.observeField("fire", "onPauseTimerFire")
    m.clockTimer.observeField("fire", "onClockTick")
    m.manualPauseTimer.observeField("fire", "onManualPauseTimerFire")
    m.ghostRetryTimer.observeField("fire", "onGhostRetryTimerFire")

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
    m.menuRows = []
    m.WARP_ROW_HEIGHT = 48
    m.WARP_VISIBLE_ROWS = 21
    ' Uniform green cells, contrasting-blue selection -- matches the web
    ' kiosk's existing work-center sidebar (options.html), not per-department
    ' colors like the rest of this screen. Blue reuses the app's existing
    ' accent color (job numbers, clock) rather than inventing a new one.
    m.WARP_ROW_COLOR = "0x2E7D32FF"
    m.WARP_ROW_SELECTED_COLOR = "0x4AAFFFFF"

    ' Schedule Window / Schedule Mode -- the same two independent, ANDed
    ' filters as the web kiosk's sidebar (update_schedule.py's
    ' VIEW_WINDOWS/SCHEDULE_MODES/matchesWindowAndMode()), minus Print
    ' Report (no printer on a Roku). Built here, not at file scope -- a bare
    ' top-level assignment is invalid BrightScript (see CODING_NOTES.md).
    m.VIEW_WINDOWS = [
        { label: "Today", days: 1, key: "1" }
        { label: "3 Days", days: 3, key: "3" }
        { label: "1 Week", days: 7, key: "7" }
        { label: "2 Weeks", days: 14, key: "14" }
        { label: "All", days: -1, key: "all" }
    ]
    m.SCHEDULE_MODES = [
        { label: "Standard", key: "standard" }
        { label: "WC Dispatch", key: "dispatch" }
    ]
    m.viewWindowKey = "all"
    m.viewDays = -1
    m.scheduleModeKey = "standard"
    m.dispatchMode = false
    ' Work Centers starts collapsed here, unlike the web kiosk (there, Print
    ' Report -- not present on this screen at all -- is the one that starts
    ' collapsed). On a real shop's work-center count (25+, confirmed in
    ' shop-schedule's own commit history), Work Centers is by far the
    ' longest section in this one shared menu, and reaching Schedule
    ' Window/Mode below it means one Down-press per row on a remote, not a
    ' mouse scroll -- the same "buries the short sections below the fold"
    ' problem that justified collapsing Print Report there, just landing on
    ' a different section here. Overridden by loadFilterSettings() once the
    ' user has actually toggled anything.
    m.menuCollapsed = { wc: true, window: false, mode: false }
    ' The last-fetched, unfiltered section list -- filteredSections() reads
    ' this fresh every time the Window/Mode filter is (re)applied, so a
    ' filter change never needs a new network fetch.
    m.rawSections = []
end sub

sub screenShown()
    m.top.setFocus(true)
    updateClock()
    m.clockTimer.control = "start"
    startGhostVideo()

    sec = CreateObject("roRegistrySection", "ScheduleConfig")
    m.serverUrl = sec.Read("serverUrl")

    loadFilterSettings()

    requestFetch()
    m.refreshTimer.control = "start"
end sub

' Persisted the same way SetupScreen.brs persists serverUrl -- a dedicated
' registry section ("ScheduleFilters", separate from "ScheduleConfig" so
' resetting the server via "options" doesn't also wipe these), read once
' here and written back only when the user actually changes something (see
' setViewWindow()/setScheduleMode()/toggleMenuSection()). Read() returns ""
' for a key never written, which is what lets each setting fall back to its
' own default below.
sub loadFilterSettings()
    sec = CreateObject("roRegistrySection", "ScheduleFilters")

    windowKey = sec.Read("view_window_days")
    if windowKey = "" then windowKey = "all"
    m.viewWindowKey = windowKey
    m.viewDays = viewDaysForKey(windowKey)

    modeKey = sec.Read("schedule_mode")
    if modeKey = "" then modeKey = "standard"
    m.scheduleModeKey = modeKey
    m.dispatchMode = (modeKey = "dispatch")

    ' "wc" defaults collapsed; the other two default expanded -- see init()'s
    ' comment on m.menuCollapsed for why.
    m.menuCollapsed.wc = (sec.Read("menu_collapsed_wc") <> "0")
    m.menuCollapsed.window = (sec.Read("menu_collapsed_window") = "1")
    m.menuCollapsed.mode = (sec.Read("menu_collapsed_mode") = "1")
end sub

sub writeFilterSetting(key as String, value as String)
    sec = CreateObject("roRegistrySection", "ScheduleFilters")
    sec.Write(key, value)
    sec.Flush()
end sub

function viewDaysForKey(key as String) as Integer
    for each w in m.VIEW_WINDOWS
        if w.key = key then return w.days
    end for
    return -1
end function

' Called by AppScene.brs's onReconfigure() before removing this screen --
' without this, a detached-but-still-alive ScheduleScreen kept polling the
' OLD server (refreshTimer/scheduleTask) and playing ghostVideo forever in
' the background after the user reconfigured to a new one, since node
' removal from contentGroup only stops rendering, not the node's own
' timers/Task. CodeRabbit catch on PR #286, sixth review pass.
sub teardown()
    try
        ' Set BEFORE stopping ghostVideo -- stopping it fires its "state"
        ' observer (onGhostVideoState()) with state="stopped", which would
        ' otherwise call startGhostVideo() right back, undoing the stop this
        ' same call is making. A pending ghostRetryTimer needs stopping too,
        ' not just the flag -- without this, a retry already in flight from
        ' an earlier video error still fires startGhostVideo() well after
        ' teardown returns. CodeRabbit catch on PR #286, seventh review pass.
        m.tornDown = true
        m.refreshTimer.control = "stop"
        m.scrollTimer.control = "stop"
        m.pauseTimer.control = "stop"
        m.clockTimer.control = "stop"
        m.manualPauseTimer.control = "stop"
        m.scheduleTask.control = "stop"
        m.ghostRetryTimer.control = "stop"
        m.ghostVideo.control = "stop"
    catch e
        print "teardown error: "; e.getMessage()
    end try
end sub

' See the ghostVideo node's comment in the XML. Content is a real bundled
' video file (media/ghost.mp4) -- Video nodes need actual content to play,
' even invisible/off-screen ones; there's no "fake playing" state.
sub startGhostVideo()
    ' Defense in depth alongside the checks in onGhostVideoState()/
    ' onGhostRetryTimerFire() -- any future caller added here inherits the
    ' same guarantee without having to remember this rule itself.
    if m.tornDown then return
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
    ' teardown() sets this right before stopping ghostVideo itself -- without
    ' this check, that stop's own "stopped" state change would land here and
    ' call startGhostVideo() right back. CodeRabbit catch on PR #286,
    ' seventh review pass.
    if m.tornDown then return
    st = m.ghostVideo.state
    if st = "error" then
        print "[GHOST] errorCode="; m.ghostVideo.errorCode; " errorMsg="; m.ghostVideo.errorMsg
        ' Retry after a delay, not immediately -- an immediate retry on a
        ' persistent/structural failure (a corrupted asset, say) would spin
        ' in a tight error -> retry -> error loop instead of backing off.
        ' "error" was previously excluded from the restart branch below
        ' entirely, so the screensaver-prevention trick this depends on
        ' (see the ghostVideo XML comment) stayed dead for the rest of the
        ' session once it failed once. CodeRabbit catch on PR #286, sixth
        ' review pass.
        m.ghostRetryTimer.control = "start"
    else if st = "finished" or st = "stopped" then
        startGhostVideo()
    end if
end sub

sub onGhostRetryTimerFire()
    startGhostVideo()
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
        ' see ScheduleTask.xml's field comment). This just makes sure
        ' m.deptColors is current for the headers buildContent() is ABOUT to
        ' build below -- it does not handle colors arriving for headers that
        ' are already on screen (fetchDeptColors() runs after scheduleData is
        ' set, so onScheduleData() can fire and build with stale/neutral
        ' colors before deptColors has caught up for this cycle). That's what
        ' the separate onDeptColors() observer below is for. CodeRabbit catch
        ' on PR #286, fifth review pass.
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

        ' Staged, not committed to m.rawSections yet -- buildContent() can
        ' reject an all-malformed response and keep the previously displayed
        ' schedule on screen. Committing unconditionally here meant a later
        ' filter change (setViewWindow()/setScheduleMode()) would rebuild
        ' from the rejected data, get rejected again, and leave the display
        ' and m.rawSections pointing at data that was never actually shown.
        ' A valid build with zero matching jobs still counts as success (the
        ' "legitimately nothing scheduled" case buildContent() itself
        ' already treats as success, not rejection) -- only commit on an
        ' actual reject. CodeRabbit catch on PR #298.
        candidateSections = data.sections
        if buildContent(filteredSections(candidateSections)) then m.rawSections = candidateSections
    catch e
        print "onScheduleData error: "; e.getMessage()
    end try
end sub

' Applies the Schedule Window/Mode filter to the given section list -- a
' section's jobs array gets a copy with only the matching jobs kept;
' buildContent()'s own existing "section.jobs.Count() > 0" check then drops
' any section that comes out empty, same as the web kiosk hiding an empty
' section's header. A section this screen can't safely iterate (malformed
' jobs) passes through untouched so buildContent()'s malformed-response
' handling still sees it exactly as the server sent it -- same for an
' individual malformed job (not an associative array): kept as-is rather
' than silently dropped, so buildJobRow()'s own crash/catch there still
' surfaces the existing display-error warning instead of the bad record
' just vanishing from a WC-Dispatch-filtered view with no sign anything was
' wrong. CodeRabbit catch on PR #298.
function filteredSections(sections as Object) as Object
    todayOrd = todayOrdinal()
    result = []
    for each section in sections
        if section.jobs <> invalid and GetInterface(section.jobs, "ifArray") <> invalid then
            keptJobs = []
            for each job in section.jobs
                if GetInterface(job, "ifAssociativeArray") = invalid then
                    keptJobs.push(job)
                else
                    currWc = job.curr_wc
                    if currWc = invalid then currWc = ""
                    if matchesWindowAndMode(section.wc, job.sch_start, currWc, todayOrd) then
                        keptJobs.push(job)
                    end if
                end if
            end for
            filtered = {
                department: section.department
                wc_group: section.wc_group
                wc: section.wc
                jobs: keptJobs
            }
            if section.backlog_days <> invalid then filtered.backlog_days = section.backlog_days
            if section.gap_days <> invalid then filtered.gap_days = section.gap_days
            result.push(filtered)
        else
            result.push(section)
        end if
    end for
    return result
end function

' Mirrors update_schedule.py's matchesWindowAndMode()/isVisible(): Schedule
' Window caps how far out a job's sch_start can be (an EXCLUSIVE upper
' bound -- a blank/unparseable sch_start always passes, same as the web
' kiosk's `if(startStr && ...)` skip), and Schedule Mode (WC Dispatch)
' additionally requires the job's current work center to match the section
' it's listed under. Independent, ANDed -- WC Dispatch narrows whatever
' date window is already selected rather than replacing it.
function matchesWindowAndMode(wc as String, startStr as Dynamic, currWc as String, todayOrd as Integer) as Boolean
    if m.viewDays <> -1 then
        startOrd = parseSchedDateOrdinal(startStr)
        if startOrd <> -1 and startOrd >= todayOrd + m.viewDays then return false
    end if
    if m.dispatchMode and currWc <> wc then return false
    return true
end function

' "dd-Mon-yy" (e.g. "05-Jan-26") -> a stable day-ordinal integer, or -1 if
' blank/unparseable. Mirrors jobboss_db.py's _parse_sched_date()'s format
' assumption (two-digit year, three-letter month). -1 specifically (not 0 or
' some far-future sentinel) because a genuinely blank/missing sch_start must
' skip the window check entirely, not sort as an arbitrary real date.
function parseSchedDateOrdinal(s as Dynamic) as Integer
    if type(s) <> "String" or Len(s) <> 9 then return -1
    monthNum = monthAbbrToNum(Mid(s, 4, 3))
    if monthNum = 0 then return -1
    day = Int(Val(Left(s, 2)))
    year = 2000 + Int(Val(Right(s, 2)))
    if day < 1 or day > 31 then return -1
    return dateOrdinal(year, monthNum, day)
end function

function monthAbbrToNum(abbr as String) as Integer
    months = ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"]
    lower = LCase(abbr)
    for i = 0 to 11
        if months[i] = lower then return i + 1
    end for
    return 0
end function

' Local calendar "today" as the same day-ordinal dateOrdinal() produces, so
' it's directly comparable to a job's parsed sch_start.
function todayOrdinal() as Integer
    dt = CreateObject("roDateTime")
    dt.ToLocalTime()
    return dateOrdinal(dt.GetYear(), dt.GetMonth(), dt.GetDayOfMonth())
end function

' Day-count since an arbitrary fixed point, via a noon ISO8601 round trip
' through roDateTime -- noon (not midnight) so the UTC/local offset on
' either side of this call can never push the instant across a day boundary
' before AsSeconds()/86400 truncates it back down. Only ever used for
' *relative* comparisons between two dates built the same way here, never
' treated as a real calendar epoch. No trailing "Z" -- Roku's documented
' FromISO8601String() formats don't include a timezone designator, and
' behavior for a format outside that list isn't guaranteed (CodeRabbit
' catch on PR #298: a silently-unparsed string would return the same
' ordinal for every date, making the Schedule Window filter a no-op).
function dateOrdinal(y as Integer, mo as Integer, d as Integer) as Integer
    iso = y.ToStr() + "-" + leftPad(mo.ToStr(), 2) + "-" + leftPad(d.ToStr(), 2) + "T12:00:00.000"
    dt = CreateObject("roDateTime")
    dt.FromISO8601String(iso)
    return dt.AsSeconds() \ 86400
end function

' Repaints already-built section headers (inline + sticky) once deptColors
' actually lands -- fetchDeptColors() runs after scheduleData is set in
' ScheduleTask.brs, so buildContent() can run (via onScheduleData() above,
' itself observing scheduleData) with stale/neutral colors before this
' cycle's deptColors has arrived. Without this, those headers would stay
' wrong until the NEXT full rebuild, up to 60s later. Direct node mutation
' via the header reference kept on each m.sectionBounds entry, not a
' rebuild -- same pattern highlightWarpMenuRow() already uses. CodeRabbit
' catch on PR #286, fifth review pass.
sub onDeptColors()
    try
        if m.scheduleTask.deptColors = invalid then return
        m.deptColors = m.scheduleTask.deptColors

        for each sectionInfo in m.sectionBounds
            colors = colorsForDept(sectionInfo.section.department)
            sectionInfo.header.getChild(0).color = colors.bg
            sectionInfo.header.getChild(1).color = colors.accent
        end for

        ' updateStickyHeader() no-ops if idx already equals
        ' m.currentSectionIdx (the normal case here -- the section hasn't
        ' changed, just its colors) -- force it to actually re-run by
        ' clearing that first, same trick applyScroll() has no need for
        ' since scrolling always changes idx itself.
        if m.currentSectionIdx >= 0 then
            idx = m.currentSectionIdx
            m.currentSectionIdx = -1
            updateStickyHeader(idx)
        end if
    catch e
        print "onDeptColors error: "; e.getMessage()
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
' Returns whether the swap actually happened -- callers that stage a
' candidate source before committing it to m.rawSections (see
' onScheduleData()) need to know whether this rejected an all-malformed
' response, so they don't commit data that was never actually displayed.
function buildContent(sections as Object) as Boolean
    ' Guards the kiosk against ever freezing on an unexpected data shape --
    ' a crash here previously took the whole render thread down with it,
    ' leaving the last frame stuck on screen with no timers left running.
    ' See CODING_NOTES.md "Resilience" for the incident this came from.
    try
        ' Build the replacement rows into a plain detached array first --
        ' NOT yet touching m.scrollContent/m.sectionBounds/m.contentHeight.
        ' A malformed section/job from the server (buildSectionHeader/
        ' buildJobRow throwing on an unexpected shape) used to be caught
        ' here too, but only *after* the old content was already wiped
        ' below -- the catch block could show an error banner but had
        ' nothing left to restore the last good schedule to. Now a failure
        ' in this loop leaves the currently displayed schedule completely
        ' untouched; the error banner shows on top of it instead of on an
        ' empty screen. CodeRabbit catch on PR #286.
        newRows = []
        newSectionBounds = []
        y = 0
        hadInputSections = (sections <> invalid and sections.Count() > 0)
        ' Tracked separately from "zero displayable sections" below -- a
        ' section with a genuinely empty (but valid) jobs array isn't
        ' malformed, just nothing to show for that work center right now.
        ' The PDF path can legitimately produce this (a work-center header
        ' with no job lines under it); treating it as malformed meant a
        ' kiosk stuck showing the error banner on every refresh until the
        ' PDF changed. CodeRabbit catch on PR #286, seventh review pass.
        malformedSections = 0
        for each section in sections
            if section.jobs = invalid then
                malformedSections = malformedSections + 1
            else if GetInterface(section.jobs, "ifArray") = invalid then
                malformedSections = malformedSections + 1
            else if section.jobs.Count() > 0 then
                header = buildSectionHeader(section, y)
                ' header kept directly on the bounds entry (not re-found by
                ' id later) so onDeptColors() below can repaint it in place --
                ' same direct-reference pattern highlightWarpMenuRow() already
                ' uses for its own row backgrounds, for the same reason.
                newSectionBounds.push({ startY: y, section: section, header: header })

                newRows.push(header)
                y = y + m.HEADER_HEIGHT

                for each job in section.jobs
                    newRows.push(buildJobRow(job, y))
                    y = y + m.ROW_HEIGHT
                end for
            end if
        end for
        newContentHeight = y

        ' Only reject when NOTHING displayed AND at least one section was
        ' actually malformed -- not a legitimate "nothing scheduled right
        ' now" (sections itself empty, or every section's jobs validly
        ' empty), which swaps in an empty schedule normally below instead.
        ' Swapping in an empty schedule over a genuinely malformed response
        ' would silently blank an otherwise-fine kiosk, the same failure
        ' mode the exception-safety above exists to prevent, just reached
        ' without throwing. Partially-malformed responses (some sections
        ' fine, others not) still display the valid ones -- only an
        ' all-bad response is rejected outright. CodeRabbit catch on PR
        ' #286, fifth and seventh review passes.
        if hadInputSections and newSectionBounds.Count() = 0 and malformedSections > 0 then
            m.errorLabel.text = "Display error building schedule -- will retry next refresh."
            m.errorBanner.visible = true
            return false
        end if

        ' Everything above succeeded -- safe to actually swap the new
        ' content in now.

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
        m.scrollContent.appendChildren(newRows)
        m.scrollTimer.control = "stop"
        m.pauseTimer.control = "stop"
        m.scrollState = "idle"
        m.sectionBounds = newSectionBounds
        m.currentSectionIdx = -1
        m.contentHeight = newContentHeight

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
        return true
    catch e
        print "buildContent error: "; e.getMessage()
        m.errorLabel.text = "Display error building schedule -- will retry next refresh."
        m.errorBanner.visible = true
        return false
    end try
end function

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
    ' "Always visible once there's at least one section" (above) means the
    ' other half has to hold too: a refresh that lands on zero populated
    ' sections left the PREVIOUS section's header stuck on screen, since the
    ' idx-out-of-range guard below returned early without ever touching
    ' .visible. CodeRabbit catch on PR #286.
    if m.sectionBounds.Count() = 0 then
        m.stickyHeader.visible = false
        m.currentSectionIdx = -1
        return
    end if
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

' Sidebar menu (OK key) -- three independently-collapsible sections (Work
' Centers / Schedule Window / Schedule Mode), flattened into one
' Up/Down-navigable row list. Built fresh every time it opens rather than
' kept live while hidden -- it's only ever on screen momentarily, and the
' underlying data (m.sectionBounds) only changes on a data refresh anyway.
' Always openable, even with zero current sections (m.sectionBounds empty)
' -- unlike the original work-center-only version, Schedule Window/Mode must
' stay reachable so a user who filtered everything out isn't stranded.
sub openWarpMenu()
    try
        m.scrollTimer.control = "stop"
        m.pauseTimer.control = "stop"
        m.manualPauseTimer.control = "stop"

        m.menuRows = buildMenuRows()
        renderMenuRows()
        m.warpMenuList.translation = [0, 0]

        m.warpMenuIdx = 0
        m.warpMenuOpen = true
        ' Stop any still-running close animation from a rapid Back-then-OK
        ' press within its ~0.2s slide-out -- left running, it would finish
        ' later and hide the menu just reopened here. Setting control="stop"
        ' changes .state synchronously (same-thread/same-component
        ' observation, unlike the cross-thread Task-field case elsewhere in
        ' this file), so this itself fires onWarpMenuCloseAnimState() inline
        ' -- safe because m.warpMenuOpen is already true above, and that
        ' observer is guarded by it. CodeRabbit catch on PR #286, sixth
        ' review pass.
        m.warpMenuCloseAnim.control = "stop"
        ' Reset off-screen before showing/animating -- guards against a
        ' prior close animation having been interrupted mid-slide (e.g. by
        ' buildContent()'s force-close) and leaving translation.x partway in.
        ' -380, matching the panel's widened 380px -- see ScheduleScreen.xml.
        m.warpMenu.translation = [-380, 0]
        m.warpMenu.visible = true
        m.warpMenuOpenAnim.control = "start"
        highlightWarpMenuRow()
    catch e
        print "openWarpMenu error: "; e.getMessage()
        m.warpMenuOpen = false
        m.warpMenu.visible = false
    end try
end sub

' Flattens the three collapsible sections into one list Up/Down can walk
' linearly -- a header row (toggleMenuSection(), via onMenuSelect()) toggles
' its own section's collapse state; an item row underneath an expanded
' header performs that item's own action. Rebuilt on open and again every
' time a header's collapse state changes -- never kept diffed/patched.
'
' The Work Centers item list is built from m.sectionBounds (what's actually
' on screen right now, post-filter), not m.rawSections (every work center
' that exists) -- unlike the web kiosk's own independent work-center filter
' list. This section is a *jump* list here, not a filter: a work center
' Schedule Window/Mode has already filtered down to zero visible jobs has
' nothing left to jump to, so listing it would be a dead selection.
function buildMenuRows() as Object
    rows = []

    rows.push({ type: "header", key: "wc", label: "WORK CENTERS", collapsed: m.menuCollapsed.wc })
    if not m.menuCollapsed.wc then
        for i = 0 to m.sectionBounds.Count() - 1
            rows.push({ type: "wc", sectionIdx: i, label: m.sectionBounds[i].section.wc })
        end for
    end if

    rows.push({ type: "header", key: "window", label: "SCHEDULE WINDOW", collapsed: m.menuCollapsed.window })
    if not m.menuCollapsed.window then
        for each w in m.VIEW_WINDOWS
            rows.push({ type: "window", windowKey: w.key, label: w.label, active: (w.key = m.viewWindowKey) })
        end for
    end if

    rows.push({ type: "header", key: "mode", label: "SCHEDULE MODE", collapsed: m.menuCollapsed.mode })
    if not m.menuCollapsed.mode then
        for each md in m.SCHEDULE_MODES
            rows.push({ type: "mode", modeKey: md.key, label: md.label, active: (md.key = m.scheduleModeKey) })
        end for
    end if

    return rows
end function

' Rebuilds warpMenuList's children from m.menuRows. Direct node references
' kept in m.warpMenuRowBgs rather than re-found by id later -- see
' highlightWarpMenuRow()'s comment for why a findNode-per-row version
' silently never highlighted anything on real hardware.
sub renderMenuRows()
    m.warpMenuList.removeChildren(m.warpMenuList.getChildren(-1, 0))
    m.warpMenuRowBgs = []
    for i = 0 to m.menuRows.Count() - 1
        rowInfo = buildMenuRowNode(m.menuRows[i], i)
        m.warpMenuList.appendChild(rowInfo.group)
        m.warpMenuRowBgs.push(rowInfo.bg)
    end for
end sub

' Header rows get a full-width dark bar with a collapse indicator (matching
' the web kiosk's own .sidebar-hdr accordion styling); item rows keep the
' original work-center-only menu's uniform green cell. "[+]"/"[-]" rather
' than a chevron glyph -- unverified whether font:SmallBoldSystemFont
' actually has one on real hardware, and plain ASCII can't render wrong.
' Window/Mode items additionally mark whichever one is actually applied
' right now (row.active) with a leading "> " -- distinct from
' highlightWarpMenuRow()'s own cursor-position highlight; the row the
' cursor is on and the row that's actually in effect are independent and
' can differ.
function buildMenuRowNode(row as Object, idx as Integer) as Object
    group = CreateObject("roSGNode", "Group")
    group.translation = [10, idx * m.WARP_ROW_HEIGHT]

    bg = CreateObject("roSGNode", "Rectangle")
    bg.width = 356
    bg.height = m.WARP_ROW_HEIGHT - 4

    label = CreateObject("roSGNode", "Label")
    label.translation = [14, 11]
    label.font = "font:SmallBoldSystemFont"
    label.color = "0xFFFFFFFF"

    if row.type = "header" then
        bg.color = "0x1A1A1AFF"
        chevron = "[+]"
        if not row.collapsed then chevron = "[-]"
        label.text = row.label + "  " + chevron
    else
        bg.color = m.WARP_ROW_COLOR
        prefix = ""
        if (row.type = "window" or row.type = "mode") and row.active then prefix = "> "
        label.text = prefix + row.label
    end if

    group.appendChild(bg)
    group.appendChild(label)
    return { group: group, bg: bg }
end function

' Snaps (not animates -- this is discrete keyboard selection, not the
' panel's own slide) the highlighted row's background and keeps it inside
' warpMenuViewport's clipped window by shifting warpMenuList's translation.
' Earlier version re-found each row's background via row.findNode("bg")
' every call instead of keeping the reference from the row-builder --
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
            else if m.menuRows[i].type = "header" then
                m.warpMenuRowBgs[i].color = "0x1A1A1AFF"
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
    ' Guarded by warpMenuOpen -- without this, openWarpMenu() stopping a
    ' still-running close anim (a rapid Back-then-OK press) would hide the
    ' menu that was just reopened, since that stop fires this same observer
    ' synchronously. CodeRabbit catch on PR #286, sixth review pass.
    if m.warpMenuCloseAnim.state = "stopped" and not m.warpMenuOpen then
        m.warpMenu.visible = false
    end if
end sub

' Dispatches the highlighted row's action: a header toggles its own
' section's collapse state and stays open; a Work Centers item jumps to
' that section (closing the menu, same as the original warp-to behavior);
' a Schedule Window/Mode item applies that filter immediately and closes.
sub onMenuSelect()
    row = m.menuRows[m.warpMenuIdx]
    if row.type = "header" then
        toggleMenuSection(row.key)
    else if row.type = "wc" then
        warpToSection(row.sectionIdx)
    else if row.type = "window" then
        setViewWindow(row.windowKey)
    else if row.type = "mode" then
        setScheduleMode(row.modeKey)
    end if
end sub

' Toggling a header never shifts rows ABOVE it, so m.warpMenuIdx (still
' pointing at this same header) stays valid after the rebuild without
' needing to re-find it.
sub toggleMenuSection(key as String)
    try
        m.menuCollapsed[key] = not m.menuCollapsed[key]
        collapsedStr = "0"
        if m.menuCollapsed[key] then collapsedStr = "1"
        writeFilterSetting("menu_collapsed_" + key, collapsedStr)
        m.menuRows = buildMenuRows()
        renderMenuRows()
        highlightWarpMenuRow()
    catch e
        print "toggleMenuSection error: "; e.getMessage()
    end try
end sub

sub warpToSection(sectionIdx as Integer)
    try
        target = m.sectionBounds[sectionIdx]
        maxScroll = m.contentHeight - m.viewportHeight

        m.scrollY = target.startY
        if m.scrollY > maxScroll then m.scrollY = maxScroll
        if m.scrollY < 0 then m.scrollY = 0
        applyScroll()
    catch e
        print "warpToSection error: "; e.getMessage()
    end try
    closeWarpMenu()
end sub

' closeWarpMenu() (called first) may put a still-scrolling display into
' "manualPaused" -- buildContent() below reads that same m.scrollState at
' its own entry and, seeing it, keeps the rebuilt content paused too before
' auto-resuming a few seconds later, same as any other manual interaction.
' Setting m.scrollY = 0 AFTER closeWarpMenu() (which doesn't touch scrollY
' itself) and BEFORE buildContent() (which reads it as the position to
' restore) is what actually resets the display to the top for this filter
' change, matching the web kiosk's own applyFilter() resetting scrollTop.
sub setViewWindow(key as String)
    try
        m.viewWindowKey = key
        m.viewDays = viewDaysForKey(key)
        writeFilterSetting("view_window_days", key)
        closeWarpMenu()
        m.scrollY = 0
        buildContent(filteredSections(m.rawSections))
    catch e
        print "setViewWindow error: "; e.getMessage()
    end try
end sub

sub setScheduleMode(key as String)
    try
        m.scheduleModeKey = key
        m.dispatchMode = (key = "dispatch")
        writeFilterSetting("schedule_mode", key)
        closeWarpMenu()
        m.scrollY = 0
        buildContent(filteredSections(m.rawSections))
    catch e
        print "setScheduleMode error: "; e.getMessage()
    end try
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
' pausing on wheel/touch input. OK opens the sidebar menu (Work Centers /
' Schedule Window / Schedule Mode) and (once open) acts on the highlighted
' row -- same button, context-dependent, matching SetupScreen.brs's
' existing OK-does-different-things-by-focus pattern rather than
' introducing a new one. Chosen over an earlier Left-to-open version that
' tested as unintuitive -- OK is the one button every remote user already
' reaches for to "do the thing."
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
            if m.warpMenuIdx < m.menuRows.Count() - 1 then
                m.warpMenuIdx = m.warpMenuIdx + 1
                highlightWarpMenuRow()
            end if
        else if key = "OK" then
            onMenuSelect()
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
