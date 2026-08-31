VERSION 1.0 CLASS
BEGIN
  MultiUse = -1  'True
END
Attribute VB_Name = "cPhoneScheduleOptimizer"
Attribute VB_GlobalNameSpace = False
Attribute VB_Creatable = False
Attribute VB_PredeclaredId = False
Attribute VB_Exposed = False
'===============================================================================
' cPhoneScheduleOptimizer.cls
' Proportional Multi-Line Phone Schedule Generator (Requirement Layer).
' Half-hourly 08:00-20:00 staffing for App_509 / App_518 across Depts/Teams.
' Late-bound Scripting.Dictionary (CreateObject) — no VBE references required.
'===============================================================================
Option Explicit

'--- Private state -------------------------------------------------------------
Private p_Departments As Collection
Private p_Global_Total_FTE As Long
Private p_Requirements As Object          ' Dict: Line -> Array(1 To 24) Long
Private p_Time_Slots As Variant           ' Array(1 To 24) String "08:00"...
Private p_Output_Schedule As Object       ' Dict: Line -> Array(1 To 24) of Dict(Team_ID->Long)

' Fairness / diagnostics
Private p_Shortfalls As Collection        ' items: "Dept|Time|Shortfall"
Private p_Jumps As Collection             ' items: "Team|Line|Time|From|To"
Private p_CapHits As Object               ' Dict: Team_ID -> Collection of time strings
Private p_CapacityShortfallFlag As Boolean

Private Const SLOT_COUNT As Long = 24
Private Const LINE_509 As String = "App_509"
Private Const LINE_518 As String = "App_518"

'===============================================================================
' Lifecycle
'===============================================================================
Private Sub Class_Initialize()
    Set p_Departments = New Collection
    Set p_Requirements = CreateObject("Scripting.Dictionary")
    Set p_Output_Schedule = CreateObject("Scripting.Dictionary")
    Set p_Shortfalls = New Collection
    Set p_Jumps = New Collection
    Set p_CapHits = CreateObject("Scripting.Dictionary")
    p_Global_Total_FTE = 0
    p_CapacityShortfallFlag = False
    Call BuildTimeSlots
End Sub

Private Sub Class_Terminate()
    Set p_Departments = Nothing
    Set p_Requirements = Nothing
    Set p_Output_Schedule = Nothing
    Set p_Shortfalls = Nothing
    Set p_Jumps = Nothing
    Set p_CapHits = Nothing
End Sub

Private Sub BuildTimeSlots()
    Dim i As Long
    Dim baseMin As Long
    Dim hrs As Long, mins As Long
    Dim arr(1 To SLOT_COUNT) As String
    baseMin = 8 * 60   ' 08:00
    For i = 1 To SLOT_COUNT
        hrs = (baseMin + (i - 1) * 30) \ 60
        mins = (baseMin + (i - 1) * 30) Mod 60
        arr(i) = Format$(hrs, "00") & ":" & Format$(mins, "00")
    Next i
    p_Time_Slots = arr
End Sub

'===============================================================================
' Public API
'===============================================================================

''' Validates inputs, computes Global FTE and weights.
Public Sub Initialize(Departments_Col As Collection, Requirements_Dict As Object)
    On Error GoTo ErrHandler
    Dim d As cDepartment
    Dim t As cTeam
    Dim lineKey As Variant
    Dim arr As Variant
    Dim lb As Long, ub As Long
    Dim i As Long

    If Departments_Col Is Nothing Then
        Err.Raise vbObjectError + 1001, "cPhoneScheduleOptimizer.Initialize", "Departments_Col is Nothing"
    End If
    If Departments_Col.Count = 0 Then
        Err.Raise vbObjectError + 1002, "cPhoneScheduleOptimizer.Initialize", "Departments_Col is empty"
    End If
    If Requirements_Dict Is Nothing Then
        Err.Raise vbObjectError + 1003, "cPhoneScheduleOptimizer.Initialize", "Requirements_Dict is Nothing"
    End If
    If Not Requirements_Dict.Exists(LINE_509) Or Not Requirements_Dict.Exists(LINE_518) Then
        Err.Raise vbObjectError + 1004, "cPhoneScheduleOptimizer.Initialize", _
            "Requirements_Dict must contain keys App_509 and App_518"
    End If

    ' Validate requirement arrays (accept 1-based or 0-based length 24)
    For Each lineKey In Array(LINE_509, LINE_518)
        arr = Requirements_Dict(CStr(lineKey))
        If Not IsArray(arr) Then
            Err.Raise vbObjectError + 1005, "cPhoneScheduleOptimizer.Initialize", _
                "Requirement for " & CStr(lineKey) & " is not an array"
        End If
        lb = LBound(arr)
        ub = UBound(arr)
        If (ub - lb + 1) <> SLOT_COUNT Then
            Err.Raise vbObjectError + 1006, "cPhoneScheduleOptimizer.Initialize", _
                "Requirement for " & CStr(lineKey) & " must have 24 slots (got " & (ub - lb + 1) & ")"
        End If
    Next lineKey

    ' Normalize to 1-based Long arrays
    Set p_Requirements = CreateObject("Scripting.Dictionary")
    For Each lineKey In Array(LINE_509, LINE_518)
        arr = Requirements_Dict(CStr(lineKey))
        lb = LBound(arr)
        Dim norm(1 To SLOT_COUNT) As Long
        For i = 1 To SLOT_COUNT
            norm(i) = CLng(arr(lb + i - 1))
            If norm(i) < 0 Then
                Err.Raise vbObjectError + 1007, "cPhoneScheduleOptimizer.Initialize", _
                    "Negative requirement at " & CStr(lineKey) & " slot " & i
            End If
        Next i
        p_Requirements.Add CStr(lineKey), norm
    Next lineKey

    Set p_Departments = Departments_Col
    p_Global_Total_FTE = 0

    For Each d In p_Departments
        d.RefreshTotalFTE
        If d.Total_FTE <= 0 Then
            Err.Raise vbObjectError + 1008, "cPhoneScheduleOptimizer.Initialize", _
                "Department " & d.Dept_ID & " has Total_FTE <= 0"
        End If
        For Each t In d.Teams
            If t.FTE_Count <= 0 Then
                Err.Raise vbObjectError + 1009, "cPhoneScheduleOptimizer.Initialize", _
                    "Team " & t.Team_ID & " has FTE_Count <= 0"
            End If
            t.Department_ID = d.Dept_ID
            t.Weight = CDbl(t.FTE_Count) / CDbl(d.Total_FTE)
        Next t
        p_Global_Total_FTE = p_Global_Total_FTE + d.Total_FTE
    Next d

    If p_Global_Total_FTE <= 0 Then
        Err.Raise vbObjectError + 1010, "cPhoneScheduleOptimizer.Initialize", "Global_Total_FTE <= 0"
    End If

    For Each d In p_Departments
        d.Weight = CDbl(d.Total_FTE) / CDbl(p_Global_Total_FTE)
    Next d

    ' Reset diagnostics / output
    Set p_Shortfalls = New Collection
    Set p_Jumps = New Collection
    Set p_CapHits = CreateObject("Scripting.Dictionary")
    Set p_Output_Schedule = CreateObject("Scripting.Dictionary")
    p_CapacityShortfallFlag = False
    Exit Sub

ErrHandler:
    Err.Raise Err.Number, Err.Source, Err.Description
End Sub

''' Main loop: Interval × Line × Dept (Hamilton) × Team (Waterfall Hamilton).
Public Function GenerateSchedule() As Boolean
    On Error GoTo ErrHandler
    Dim tSlot As Long
    Dim lineName As Variant
    Dim req As Long
    Dim d As cDepartment
    Dim team As cTeam
    Dim nDept As Long
    Dim i As Long, j As Long

    Dim deptWeights() As Double
    Dim deptCaps() As Long
    Dim deptIDs() As String
    Dim dictDeptAllocs As Object
    Dim dictTeamAllocs As Object
    Dim slotTeamDict As Object
    Dim lineSlots As Variant
    Dim reqArr As Variant

    If p_Departments Is Nothing Or p_Departments.Count = 0 Then
        Err.Raise vbObjectError + 1101, "GenerateSchedule", "Call Initialize first"
    End If

    nDept = p_Departments.Count
    ReDim deptWeights(1 To nDept)
    ReDim deptCaps(1 To nDept)
    ReDim deptIDs(1 To nDept)

    i = 0
    For Each d In p_Departments
        i = i + 1
        deptWeights(i) = d.Weight
        deptCaps(i) = d.Total_FTE
        deptIDs(i) = d.Dept_ID
    Next d

    ' Init output structure: Line -> Array(1 To 24) of Dictionary(Team_ID -> Long)
    Set p_Output_Schedule = CreateObject("Scripting.Dictionary")
    For Each lineName In Array(LINE_509, LINE_518)
        Dim slotArr(1 To SLOT_COUNT) As Object
        For tSlot = 1 To SLOT_COUNT
            Set slotArr(tSlot) = CreateObject("Scripting.Dictionary")
            For Each d In p_Departments
                For Each team In d.Teams
                    slotArr(tSlot).Add team.Team_ID, 0&
                Next team
            Next d
        Next tSlot
        p_Output_Schedule.Add CStr(lineName), slotArr
    Next lineName

    Set p_Shortfalls = New Collection
    Set p_Jumps = New Collection
    Set p_CapHits = CreateObject("Scripting.Dictionary")
    p_CapacityShortfallFlag = False

    For tSlot = 1 To SLOT_COUNT
        For Each lineName In Array(LINE_509, LINE_518)
            reqArr = p_Requirements(CStr(lineName))
            req = CLng(reqArr(tSlot))
            lineSlots = p_Output_Schedule(CStr(lineName))
            Set slotTeamDict = lineSlots(tSlot)

            If req = 0 Then
                ' Already zeroed at init
            Else
                '--- Dept-level Hamilton (caps = dept total FTE) ---
                Set dictDeptAllocs = HamiltonApportion(req, deptWeights, deptCaps, deptIDs, _
                    CStr(lineName), CStr(p_Time_Slots(tSlot)), "DEPT")

                '--- Team-level within each dept ---
                For Each d In p_Departments
                    Dim deptReq As Long
                    deptReq = 0
                    If dictDeptAllocs.Exists(d.Dept_ID) Then
                        deptReq = CLng(dictDeptAllocs(d.Dept_ID))
                    End If

                    If deptReq = 0 Then
                        ' leave team allocs at 0
                    Else
                        Dim nTeam As Long
                        nTeam = d.Teams.Count
                        Dim teamWeights() As Double
                        Dim teamCaps() As Long
                        Dim teamIDs() As String
                        ReDim teamWeights(1 To nTeam)
                        ReDim teamCaps(1 To nTeam)
                        ReDim teamIDs(1 To nTeam)
                        j = 0
                        For Each team In d.Teams
                            j = j + 1
                            teamWeights(j) = team.Weight
                            teamCaps(j) = team.FTE_Count
                            teamIDs(j) = team.Team_ID
                        Next team

                        Set dictTeamAllocs = HamiltonApportion(deptReq, teamWeights, teamCaps, teamIDs, _
                            CStr(lineName), CStr(p_Time_Slots(tSlot)), "TEAM:" & d.Dept_ID)

                        Dim tid As Variant
                        For Each tid In dictTeamAllocs.Keys
                            slotTeamDict(CStr(tid)) = CLng(dictTeamAllocs(tid))
                            ' Cap-hit logging
                            For Each team In d.Teams
                                If team.Team_ID = CStr(tid) Then
                                    If CLng(dictTeamAllocs(tid)) = team.FTE_Count And team.FTE_Count > 0 Then
                                        Call LogCapHit(team.Team_ID, CStr(p_Time_Slots(tSlot)))
                                    End If
                                    Exit For
                                End If
                            Next team
                        Next tid
                    End If
                Next d
            End If

            ' Write back (Dictionary is ByRef object inside array — already mutated)
            lineSlots(tSlot) = slotTeamDict
            p_Output_Schedule(CStr(lineName)) = lineSlots
        Next lineName
    Next tSlot

    Call PostProcessValidation
    GenerateSchedule = True
    Exit Function

ErrHandler:
    GenerateSchedule = False
    Err.Raise Err.Number, Err.Source, Err.Description
End Function

''' Writes Requirement_Schedule, Shift_Building_Helper, Fairness_Report.
Public Sub ExportToSheets(Optional wb As Workbook = Nothing)
    On Error GoTo ErrHandler
    Dim targetWb As Workbook
    If wb Is Nothing Then
        Set targetWb = ThisWorkbook
    Else
        Set targetWb = wb
    End If

    Call WriteRequirementSchedule(targetWb)
    Call WriteShiftBuildingHelper(targetWb)
    Call WriteFairnessReport(targetWb)
    Exit Sub

ErrHandler:
    Err.Raise Err.Number, Err.Source, Err.Description
End Sub

''' Read allocated FTE for assertions / external use.
Public Function GetAllocation(ByVal lineName As String, ByVal slotIndex As Long, ByVal teamID As String) As Long
    Dim lineSlots As Variant
    Dim slotDict As Object
    GetAllocation = 0
    If Not p_Output_Schedule.Exists(lineName) Then Exit Function
    If slotIndex < 1 Or slotIndex > SLOT_COUNT Then Exit Function
    lineSlots = p_Output_Schedule(lineName)
    Set slotDict = lineSlots(slotIndex)
    If slotDict.Exists(teamID) Then GetAllocation = CLng(slotDict(teamID))
End Function

Public Property Get GlobalTotalFTE() As Long
    GlobalTotalFTE = p_Global_Total_FTE
End Property

Public Property Get TimeSlot(ByVal index As Long) As String
    TimeSlot = CStr(p_Time_Slots(index))
End Property

'===============================================================================
' Hamilton Apportionment + Iterative Waterfall Cap Redistribution
'===============================================================================

''' Returns Scripting.Dictionary(Key=ID, Value=Allocated Long).
''' Caps enforced; remainder redistributed among non-full entities by largest remainder.
Private Function HamiltonApportion(ByVal Total_Req As Long, _
                                   Weights() As Double, _
                                   Caps() As Long, _
                                   IDs() As String, _
                                   Optional ByVal lineName As String = "", _
                                   Optional ByVal timeLabel As String = "", _
                                   Optional ByVal contextTag As String = "") As Object

    Dim result As Object
    Set result = CreateObject("Scripting.Dictionary")

    Dim n As Long
    Dim i As Long
    Dim lb As Long, ub As Long
    lb = LBound(Weights)
    ub = UBound(Weights)
    n = ub - lb + 1

    If Total_Req <= 0 Or n <= 0 Then
        For i = lb To ub
            result.Add IDs(i), 0&
        Next i
        Set HamiltonApportion = result
        Exit Function
    End If

    ' Working arrays (1-based copy)
    Dim weight(1 To 1000) As Double
    Dim cap(1 To 1000) As Long
    Dim id(1 To 1000) As String
    Dim alloc(1 To 1000) As Long
    Dim rem(1 To 1000) As Double
    Dim isFull(1 To 1000) As Boolean
    Dim active(1 To 1000) As Boolean
    Dim ideal As Double
    Dim sumAlloc As Long
    Dim remSlots As Long
    Dim safety As Long
    Dim sumActiveWeight As Double

    If n > 1000 Then
        Err.Raise vbObjectError + 1201, "HamiltonApportion", "Too many entities (max 1000)"
    End If

    For i = 1 To n
        weight(i) = Weights(lb + i - 1)
        cap(i) = Caps(lb + i - 1)
        id(i) = IDs(lb + i - 1)
        alloc(i) = 0
        rem(i) = 0
        isFull(i) = False
        active(i) = True
    Next i

    Dim pending As Long
    pending = Total_Req
    safety = 0

    Do While pending > 0 And safety < 500
        safety = safety + 1

        ' Renormalize weights among active (non-full) entities
        sumActiveWeight = 0
        For i = 1 To n
            If active(i) And Not isFull(i) Then
                sumActiveWeight = sumActiveWeight + weight(i)
            End If
        Next i

        If sumActiveWeight <= 0# Then
            ' No capacity left among active set
            Exit Do
        End If

        ' Fresh floor allocation for this waterfall pass on the *pending* remainder
        Dim passAlloc(1 To 1000) As Long
        Dim passRem(1 To 1000) As Double
        Dim passSum As Long
        passSum = 0

        For i = 1 To n
            passAlloc(i) = 0
            passRem(i) = 0
            If active(i) And Not isFull(i) Then
                ideal = CDbl(pending) * (weight(i) / sumActiveWeight)
                ' Floor toward zero (non-negative ideals)
                passAlloc(i) = Int(ideal)   ' VBA Int truncates toward -inf; ideal>=0 so OK
                passRem(i) = ideal - CDbl(passAlloc(i))
                ' Cap within this pass
                If passAlloc(i) > (cap(i) - alloc(i)) Then
                    passAlloc(i) = cap(i) - alloc(i)
                    If passAlloc(i) < 0 Then passAlloc(i) = 0
                    isFull(i) = True
                    passRem(i) = -1#   ' deprioritize for remainder
                End If
                passSum = passSum + passAlloc(i)
            End If
        Next i

        ' Apply pass floors to cumulative alloc
        For i = 1 To n
            alloc(i) = alloc(i) + passAlloc(i)
            If alloc(i) >= cap(i) Then
                alloc(i) = cap(i)
                isFull(i) = True
            End If
            rem(i) = passRem(i)
        Next i

        remSlots = pending - passSum
        If remSlots < 0 Then remSlots = 0

        ' Largest Remainder: give +1 to non-full by rem desc until remSlots=0
        Do While remSlots > 0
            Dim bestIdx As Long
            Dim bestRem As Double
            bestIdx = -1
            bestRem = -2#

            For i = 1 To n
                If Not isFull(i) And active(i) And alloc(i) < cap(i) Then
                    If rem(i) > bestRem Then
                        bestRem = rem(i)
                        bestIdx = i
                    ElseIf rem(i) = bestRem And bestIdx > 0 Then
                        ' Tie-break: higher weight, then ID order already implied by index
                        If weight(i) > weight(bestIdx) Then
                            bestIdx = i
                        End If
                    End If
                End If
            Next i

            If bestIdx < 0 Then Exit Do

            alloc(bestIdx) = alloc(bestIdx) + 1
            rem(bestIdx) = -1#   ' already used this remainder token
            remSlots = remSlots - 1

            If alloc(bestIdx) >= cap(bestIdx) Then
                alloc(bestIdx) = cap(bestIdx)
                isFull(bestIdx) = True
            End If
        Loop

        ' How much still unallocated vs total request?
        sumAlloc = 0
        For i = 1 To n
            sumAlloc = sumAlloc + alloc(i)
        Next i
        pending = Total_Req - sumAlloc

        ' If still pending but all capped, stop
        Dim anyOpen As Boolean
        anyOpen = False
        For i = 1 To n
            If Not isFull(i) And alloc(i) < cap(i) Then
                anyOpen = True
                Exit For
            End If
        Next i
        If Not anyOpen Then Exit Do

        ' If remSlots leftover with open seats but rem sorting exhausted (all rem=-1),
        ' reset rem for open teams using residual ideal for another LR pass
        If pending > 0 And anyOpen Then
            Dim openCapLeft As Long
            openCapLeft = 0
            For i = 1 To n
                If Not isFull(i) Then openCapLeft = openCapLeft + (cap(i) - alloc(i))
            Next i
            If openCapLeft <= 0 Then Exit Do
            ' Continue outer loop to redistribute remaining pending
        End If
    Loop

    sumAlloc = 0
    For i = 1 To n
        If alloc(i) > cap(i) Then alloc(i) = cap(i)
        sumAlloc = sumAlloc + alloc(i)
        result.Add id(i), alloc(i)
    Next i

    If sumAlloc < Total_Req Then
        p_CapacityShortfallFlag = True
        Dim shortfall As Long
        shortfall = Total_Req - sumAlloc
        ' Log shortfall — for TEAM context extract dept from tag; for DEPT log each?
        If Left$(contextTag, 5) = "TEAM:" Then
            Dim deptId As String
            deptId = Mid$(contextTag, 6)
            p_Shortfalls.Add deptId & "|" & timeLabel & "|" & CStr(shortfall) & "|" & lineName
        ElseIf contextTag = "DEPT" Then
            ' Global demand exceeded sum of dept caps
            p_Shortfalls.Add "GLOBAL|" & timeLabel & "|" & CStr(shortfall) & "|" & lineName
        End If
    End If

    Set HamiltonApportion = result
End Function

'===============================================================================
' Post-processing
'===============================================================================
Private Sub PostProcessValidation()
    Dim d As cDepartment
    Dim team As cTeam
    Dim lineName As Variant
    Dim tSlot As Long
    Dim cur As Long, prev As Long
    Dim lineSlots As Variant
    Dim slotDict As Object

    For Each lineName In Array(LINE_509, LINE_518)
        lineSlots = p_Output_Schedule(CStr(lineName))
        For Each d In p_Departments
            For Each team In d.Teams
                prev = -1
                For tSlot = 1 To SLOT_COUNT
                    Set slotDict = lineSlots(tSlot)
                    cur = 0
                    If slotDict.Exists(team.Team_ID) Then cur = CLng(slotDict(team.Team_ID))
                    If prev >= 0 Then
                        If Abs(cur - prev) > 1 Then
                            p_Jumps.Add team.Team_ID & "|" & CStr(lineName) & "|" & _
                                CStr(p_Time_Slots(tSlot)) & "|" & CStr(prev) & "|" & CStr(cur)
                        End If
                    End If
                    prev = cur
                Next tSlot
            Next team
        Next d
    Next lineName
End Sub

Private Sub LogCapHit(ByVal teamID As String, ByVal timeLabel As String)
    Dim col As Collection
    If Not p_CapHits.Exists(teamID) Then
        Set col = New Collection
        p_CapHits.Add teamID, col
    Else
        Set col = p_CapHits(teamID)
    End If
    col.Add timeLabel
End Sub

'===============================================================================
' Sheet writers (bulk Array dump)
'===============================================================================
Private Function EnsureSheet(wb As Workbook, ByVal sheetName As String) As Worksheet
    Dim ws As Worksheet
    On Error Resume Next
    Set ws = wb.Worksheets(sheetName)
    On Error GoTo 0
    If ws Is Nothing Then
        Set ws = wb.Worksheets.Add(After:=wb.Worksheets(wb.Worksheets.Count))
        ws.Name = sheetName
    Else
        ws.Cells.Clear
    End If
    Set EnsureSheet = ws
End Function

Private Sub WriteRequirementSchedule(wb As Workbook)
    Dim ws As Worksheet
    Set ws = EnsureSheet(wb, "Requirement_Schedule")

    Dim d As cDepartment
    Dim team As cTeam
    Dim lineName As Variant
    Dim tSlot As Long
    Dim rowCount As Long
    Dim nTeams As Long

    nTeams = 0
    For Each d In p_Departments
        nTeams = nTeams + d.Teams.Count
    Next d

    ' 24 × 2 × NTeams + header
    rowCount = SLOT_COUNT * 2 * nTeams
    Dim arr() As Variant
    ReDim arr(1 To rowCount + 1, 1 To 5)

    arr(1, 1) = "Time"
    arr(1, 2) = "Line"
    arr(1, 3) = "Dept_ID"
    arr(1, 4) = "Team_ID"
    arr(1, 5) = "Required_FTE"

    Dim r As Long
    r = 2
    For tSlot = 1 To SLOT_COUNT
        For Each lineName In Array(LINE_509, LINE_518)
            Dim lineSlots As Variant
            Dim slotDict As Object
            lineSlots = p_Output_Schedule(CStr(lineName))
            Set slotDict = lineSlots(tSlot)
            For Each d In p_Departments
                For Each team In d.Teams
                    arr(r, 1) = p_Time_Slots(tSlot)
                    arr(r, 2) = CStr(lineName)
                    arr(r, 3) = d.Dept_ID
                    arr(r, 4) = team.Team_ID
                    If slotDict.Exists(team.Team_ID) Then
                        arr(r, 5) = CLng(slotDict(team.Team_ID))
                    Else
                        arr(r, 5) = 0
                    End If
                    r = r + 1
                Next team
            Next d
        Next lineName
    Next tSlot

    ws.Range(ws.Cells(1, 1), ws.Cells(rowCount + 1, 5)).Value = arr
    ws.Columns("A:E").AutoFit
End Sub

Private Sub WriteShiftBuildingHelper(wb As Workbook)
    Dim ws As Worksheet
    Set ws = EnsureSheet(wb, "Shift_Building_Helper")

    ' Header
    Dim headers As Variant
    headers = Array("Team_ID", "Line", "Block_Start", "Block_End", "Block_Min_FTE", "Block_Slots_Count", "Block_Type")

    Dim outRows As Collection
    Set outRows = New Collection

    Dim d As cDepartment
    Dim team As cTeam
    Dim lineName As Variant
    Dim tSlot As Long
    Dim fteCurve(1 To SLOT_COUNT) As Long
    Dim lineSlots As Variant
    Dim slotDict As Object

    For Each d In p_Departments
        For Each team In d.Teams
            For Each lineName In Array(LINE_509, LINE_518)
                lineSlots = p_Output_Schedule(CStr(lineName))
                For tSlot = 1 To SLOT_COUNT
                    Set slotDict = lineSlots(tSlot)
                    If slotDict.Exists(team.Team_ID) Then
                        fteCurve(tSlot) = CLng(slotDict(team.Team_ID))
                    Else
                        fteCurve(tSlot) = 0
                    End If
                Next tSlot
                Call AppendBlocksForCurve(outRows, team.Team_ID, CStr(lineName), fteCurve)
            Next lineName
        Next team
    Next d

    Dim nOut As Long
    nOut = outRows.Count
    Dim arr() As Variant
    ReDim arr(1 To nOut + 1, 1 To 7)
    Dim c As Long
    For c = 1 To 7
        arr(1, c) = headers(c - 1)
    Next c

    Dim item As Variant
    Dim r As Long
    r = 2
    For Each item In outRows
        Dim parts() As String
        parts = Split(CStr(item), "|")
        Dim k As Long
        For k = 0 To 6
            If IsNumeric(parts(k)) And k >= 4 And k <= 5 Then
                arr(r, k + 1) = CLng(parts(k))
            Else
                arr(r, k + 1) = parts(k)
            End If
        Next k
        r = r + 1
    Next item

    If nOut = 0 Then
        ws.Range("A1:G1").Value = headers
    Else
        ws.Range(ws.Cells(1, 1), ws.Cells(nOut + 1, 7)).Value = arr
    End If
    ws.Columns("A:G").AutoFit
End Sub

''' Group half-hourly curve into maximal 4-slot (2hr) windows where Min(FTE)>0,
''' plus partial blocks (<4) at edges / gaps.
Private Sub AppendBlocksForCurve(ByRef outRows As Collection, _
                                 ByVal teamID As String, _
                                 ByVal lineName As String, _
                                 ByRef fteCurve() As Long)
    Dim t As Long
    Dim startPos As Long
    Dim winStart As Long
    Dim i As Long
    Dim minFte As Long
    Dim blockEndTime As String
    Dim endHour As Long, endMin As Long
    Dim baseMin As Long

    ' Find contiguous positive regions, then tile 4-slot windows inside each
    t = 1
    Do While t <= SLOT_COUNT
        If fteCurve(t) <= 0 Then
            t = t + 1
        Else
            startPos = t
            Do While t <= SLOT_COUNT And fteCurve(t) > 0
                t = t + 1
            Loop
            ' region [startPos, t-1]
            Dim regionEnd As Long
            regionEnd = t - 1
            winStart = startPos
            Do While winStart + 3 <= regionEnd
                minFte = fteCurve(winStart)
                For i = winStart + 1 To winStart + 3
                    If fteCurve(i) < minFte Then minFte = fteCurve(i)
                Next i
                If minFte > 0 Then
                    blockEndTime = SlotEndLabel(winStart + 3)
                    outRows.Add teamID & "|" & lineName & "|" & CStr(p_Time_Slots(winStart)) & "|" & _
                        blockEndTime & "|" & CStr(minFte) & "|4|Full_2hr"
                End If
                winStart = winStart + 4
            Loop
            ' Partial leftover at end of contiguous region
            If winStart <= regionEnd Then
                minFte = fteCurve(winStart)
                For i = winStart + 1 To regionEnd
                    If fteCurve(i) < minFte Then minFte = fteCurve(i)
                Next i
                blockEndTime = SlotEndLabel(regionEnd)
                outRows.Add teamID & "|" & lineName & "|" & CStr(p_Time_Slots(winStart)) & "|" & _
                    blockEndTime & "|" & CStr(minFte) & "|" & CStr(regionEnd - winStart + 1) & "|Partial"
            End If
        End If
    Loop
End Sub

''' End time of a half-hour slot (slot covering HH:MM ends at HH:MM+30).
Private Function SlotEndLabel(ByVal slotIndex As Long) As String
    Dim baseMin As Long
    Dim totalMin As Long
    Dim hrs As Long, mins As Long
    baseMin = 8 * 60
    totalMin = baseMin + slotIndex * 30   ' end of slotIndex (1-based)
    hrs = totalMin \ 60
    mins = totalMin Mod 60
    SlotEndLabel = Format$(hrs, "00") & ":" & Format$(mins, "00")
End Function

Private Sub WriteFairnessReport(wb As Workbook)
    Dim ws As Worksheet
    Set ws = EnsureSheet(wb, "Fairness_Report")

    Dim d As cDepartment
    Dim team As cTeam
    Dim lineName As Variant
    Dim tSlot As Long
    Dim lineSlots As Variant
    Dim slotDict As Object

    '--- Section 1: Global Utilization ---
    ws.Range("A1").Value = "GLOBAL UTILIZATION"
    ws.Range("A2").Value = "Team_ID"
    ws.Range("B2").Value = "FTE_Count"
    ws.Range("C2").Value = "Theoretical_Max"
    ws.Range("D2").Value = "Actual_Allocated_Hours"
    ws.Range("E2").Value = "Utilization_%"
    ws.Range("F2").Value = "Dept_Avg_Util_%"
    ws.Range("G2").Value = "Variance"

    ' Precompute actual allocated half-hour FTEs (sum over lines & slots)
    Dim actualByTeam As Object
    Set actualByTeam = CreateObject("Scripting.Dictionary")
    Dim deptUtilSum As Object
    Dim deptUtilCnt As Object
    Set deptUtilSum = CreateObject("Scripting.Dictionary")
    Set deptUtilCnt = CreateObject("Scripting.Dictionary")

    For Each d In p_Departments
        For Each team In d.Teams
            Dim totalAlloc As Long
            totalAlloc = 0
            For Each lineName In Array(LINE_509, LINE_518)
                lineSlots = p_Output_Schedule(CStr(lineName))
                For tSlot = 1 To SLOT_COUNT
                    Set slotDict = lineSlots(tSlot)
                    If slotDict.Exists(team.Team_ID) Then
                        totalAlloc = totalAlloc + CLng(slotDict(team.Team_ID))
                    End If
                Next tSlot
            Next lineName
            actualByTeam.Add team.Team_ID, totalAlloc
        Next team
    Next d

    ' Dept average util
    For Each d In p_Departments
        Dim sumUtil As Double
        Dim cnt As Long
        sumUtil = 0
        cnt = 0
        For Each team In d.Teams
            Dim theor As Long
            Dim act As Long
            Dim util As Double
            theor = team.FTE_Count * SLOT_COUNT
            act = CLng(actualByTeam(team.Team_ID))
            If theor > 0 Then
                util = CDbl(act) / CDbl(theor) * 100#
            Else
                util = 0
            End If
            sumUtil = sumUtil + util
            cnt = cnt + 1
        Next team
        If cnt > 0 Then
            deptUtilSum.Add d.Dept_ID, sumUtil / CDbl(cnt)
        Else
            deptUtilSum.Add d.Dept_ID, 0#
        End If
    Next d

    Dim r As Long
    r = 3
    For Each d In p_Departments
        Dim deptAvg As Double
        deptAvg = CDbl(deptUtilSum(d.Dept_ID))
        For Each team In d.Teams
            theor = team.FTE_Count * SLOT_COUNT
            act = CLng(actualByTeam(team.Team_ID))
            If theor > 0 Then
                util = CDbl(act) / CDbl(theor) * 100#
            Else
                util = 0
            End If
            ws.Cells(r, 1).Value = team.Team_ID
            ws.Cells(r, 2).Value = team.FTE_Count
            ws.Cells(r, 3).Value = theor
            ws.Cells(r, 4).Value = act
            ws.Cells(r, 5).Value = Round(util, 2)
            ws.Cells(r, 6).Value = Round(deptAvg, 2)
            ws.Cells(r, 7).Value = Round(util - deptAvg, 2)
            r = r + 1
        Next team
    Next d

    '--- Section 2: Per-Interval Max Deviation from Ideal Share ---
    r = r + 1
    ws.Cells(r, 1).Value = "PER_INTERVAL_MAX_DEVIATION"
    r = r + 1
    ws.Cells(r, 1).Value = "Time"
    ws.Cells(r, 2).Value = "Line"
    ws.Cells(r, 3).Value = "Max_|ActualShare-IdealShare|"
    r = r + 1

    For tSlot = 1 To SLOT_COUNT
        For Each lineName In Array(LINE_509, LINE_518)
            Dim reqArr As Variant
            Dim reqVal As Long
            reqArr = p_Requirements(CStr(lineName))
            reqVal = CLng(reqArr(tSlot))
            Dim maxDev As Double
            maxDev = 0
            If reqVal > 0 Then
                lineSlots = p_Output_Schedule(CStr(lineName))
                Set slotDict = lineSlots(tSlot)
                For Each d In p_Departments
                    For Each team In d.Teams
                        Dim actualShare As Double
                        Dim idealShare As Double
                        Dim allocVal As Long
                        allocVal = 0
                        If slotDict.Exists(team.Team_ID) Then allocVal = CLng(slotDict(team.Team_ID))
                        actualShare = CDbl(allocVal) / CDbl(reqVal)
                        idealShare = d.Weight * team.Weight
                        If Abs(actualShare - idealShare) > maxDev Then
                            maxDev = Abs(actualShare - idealShare)
                        End If
                    Next team
                Next d
            End If
            ws.Cells(r, 1).Value = p_Time_Slots(tSlot)
            ws.Cells(r, 2).Value = CStr(lineName)
            ws.Cells(r, 3).Value = Round(maxDev, 6)
            r = r + 1
        Next lineName
    Next tSlot

    '--- Section 3: Caps Hit Log ---
    r = r + 1
    ws.Cells(r, 1).Value = "CAPS_HIT_LOG"
    r = r + 1
    ws.Cells(r, 1).Value = "Team_ID"
    ws.Cells(r, 2).Value = "Interval_Count_Hit_Cap"
    ws.Cells(r, 3).Value = "List_of_Times"
    r = r + 1

    Dim tid As Variant
    If p_CapHits.Count > 0 Then
        For Each tid In p_CapHits.Keys
            Dim timesCol As Collection
            Set timesCol = p_CapHits(tid)
            Dim timesList As String
            timesList = ""
            Dim ti As Long
            For ti = 1 To timesCol.Count
                If ti > 1 Then timesList = timesList & ", "
                timesList = timesList & timesCol(ti)
            Next ti
            ws.Cells(r, 1).Value = CStr(tid)
            ws.Cells(r, 2).Value = timesCol.Count
            ws.Cells(r, 3).Value = timesList
            r = r + 1
        Next tid
    Else
        ws.Cells(r, 1).Value = "(none)"
        r = r + 1
    End If

    '--- Section 4: Capacity Shortfalls ---
    r = r + 1
    ws.Cells(r, 1).Value = "CAPACITY_SHORTFALLS"
    r = r + 1
    ws.Cells(r, 1).Value = "Dept_ID"
    ws.Cells(r, 2).Value = "Time"
    ws.Cells(r, 3).Value = "Shortfall_FTE"
    ws.Cells(r, 4).Value = "Line"
    ws.Cells(r, 5).Value = "Message"
    r = r + 1

    Dim sItem As Variant
    If p_Shortfalls.Count > 0 Then
        For Each sItem In p_Shortfalls
            Dim sp() As String
            sp = Split(CStr(sItem), "|")
            ws.Cells(r, 1).Value = sp(0)
            ws.Cells(r, 2).Value = sp(1)
            ws.Cells(r, 3).Value = CLng(sp(2))
            If UBound(sp) >= 3 Then ws.Cells(r, 4).Value = sp(3)
            ws.Cells(r, 5).Value = "WARNING: Insufficient Capacity"
            r = r + 1
        Next sItem
    Else
        ws.Cells(r, 1).Value = "(none)"
        r = r + 1
    End If

    '--- Section 5: Continuity Jumps ---
    r = r + 1
    ws.Cells(r, 1).Value = "CONTINUITY_JUMPS"
    r = r + 1
    ws.Cells(r, 1).Value = "Team_ID"
    ws.Cells(r, 2).Value = "Line"
    ws.Cells(r, 3).Value = "Time"
    ws.Cells(r, 4).Value = "From"
    ws.Cells(r, 5).Value = "To"
    r = r + 1

    Dim jItem As Variant
    If p_Jumps.Count > 0 Then
        For Each jItem In p_Jumps
            Dim jp() As String
            jp = Split(CStr(jItem), "|")
            ws.Cells(r, 1).Value = jp(0)
            ws.Cells(r, 2).Value = jp(1)
            ws.Cells(r, 3).Value = jp(2)
            ws.Cells(r, 4).Value = CLng(jp(3))
            ws.Cells(r, 5).Value = CLng(jp(4))
            r = r + 1
        Next jItem
    Else
        ws.Cells(r, 1).Value = "(none)"
    End If

    ws.Columns("A:G").AutoFit
End Sub

''' Debug summary for Immediate Window.
Public Sub PrintFairnessSummary()
    Dim d As cDepartment
    Dim team As cTeam
    Debug.Print "=== Fairness Summary ==="
    Debug.Print "Global_Total_FTE=" & p_Global_Total_FTE
    Debug.Print "Shortfalls=" & p_Shortfalls.Count & " | Jumps=" & p_Jumps.Count & " | CapHitTeams=" & p_CapHits.Count
    Dim s As Variant
    For Each s In p_Shortfalls
        Debug.Print "SHORTFALL: " & CStr(s)
    Next s
End Sub
