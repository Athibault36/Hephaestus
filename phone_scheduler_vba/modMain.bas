Attribute VB_Name = "modMain"
'===============================================================================
' modMain.bas  (also referred to as the phone scheduler entry module)
' Run_Test_Case  — exercises the required assertion suite
' Run_Production — hook for live workbook data (extend as needed)
'===============================================================================
Option Explicit

'-------------------------------------------------------------------------------
' TEST CASE (MUST PASS)
' Dept1: A=18, B=2 (20) | Dept2: C=10 | Dept3: D=10 | Global=40
' App_509 slots 1-18 = 20; 19-24 = 0 | App_518 all 0
' Assert Slot1 App_509: A=9, B=1, C=5, D=5
' Cap edge: Req=45 -> A=18, B=2, shortfall logged
'-------------------------------------------------------------------------------
Public Sub Run_Test_Case()
    On Error GoTo ErrHandler

    Dim depts As Collection
    Dim req As Object
    Dim opt As cPhoneScheduleOptimizer
    Dim i As Long
    Dim arr509(1 To 24) As Long
    Dim arr518(1 To 24) As Long

    Set depts = BuildTestDepartments()
    Set req = CreateObject("Scripting.Dictionary")

    For i = 1 To 18
        arr509(i) = 20
    Next i
    For i = 19 To 24
        arr509(i) = 0
    Next i
    For i = 1 To 24
        arr518(i) = 0
    Next i

    req.Add "App_509", arr509
    req.Add "App_518", arr518

    Set opt = New cPhoneScheduleOptimizer
    opt.Initialize depts, req

    If Not opt.GenerateSchedule() Then
        MsgBox "GenerateSchedule returned False", vbCritical
        Exit Sub
    End If

    opt.ExportToSheets ThisWorkbook
    opt.PrintFairnessSummary

    '--- Primary assertions (Slot 1 / 08:00 / App_509) ---
    Dim a As Long, b As Long, c As Long, dAlloc As Long
    a = opt.GetAllocation("App_509", 1, "D1_Team_A")
    b = opt.GetAllocation("App_509", 1, "D1_Team_B")
    c = opt.GetAllocation("App_509", 1, "D2_Team_C")
    dAlloc = opt.GetAllocation("App_509", 1, "D3_Team_D")

    Debug.Print "Slot1 App_509 -> A=" & a & " B=" & b & " C=" & c & " D=" & dAlloc

    Debug.Assert a = 9
    Debug.Assert b = 1
    Debug.Assert c = 5
    Debug.Assert dAlloc = 5

    If a <> 9 Or b <> 1 Then
        MsgBox "ASSERT FAIL: Expected Team_A=9, Team_B=1 at 08:00 App_509. Got A=" & a & " B=" & b, vbCritical
        Exit Sub
    End If
    If c <> 5 Or dAlloc <> 5 Then
        MsgBox "ASSERT FAIL: Expected C=5, D=5. Got C=" & c & " D=" & dAlloc, vbCritical
        Exit Sub
    End If

    '--- Cap-hit edge case (Req=45 at slot 1) ---
    Call Run_CapHit_EdgeCase

    MsgBox "Run_Test_Case PASSED." & vbCrLf & _
           "Requirement_Schedule / Shift_Building_Helper / Fairness_Report written.", _
           vbInformation, "Phone Scheduler"
    Exit Sub

ErrHandler:
    MsgBox "Run_Test_Case ERROR " & Err.Number & ": " & Err.Description, vbCritical
End Sub

Private Function BuildTestDepartments() As Collection
    Dim col As Collection
    Dim d1 As cDepartment, d2 As cDepartment, d3 As cDepartment
    Dim tA As cTeam, tB As cTeam, tC As cTeam, tD As cTeam

    Set col = New Collection

    Set d1 = New cDepartment
    d1.Dept_ID = "Dept_1"
    Set tA = New cTeam
    tA.Team_ID = "D1_Team_A"
    tA.Department_ID = "Dept_1"
    tA.FTE_Count = 18
    d1.Teams.Add tA

    Set tB = New cTeam
    tB.Team_ID = "D1_Team_B"
    tB.Department_ID = "Dept_1"
    tB.FTE_Count = 2
    d1.Teams.Add tB
    d1.RefreshTotalFTE
    col.Add d1

    Set d2 = New cDepartment
    d2.Dept_ID = "Dept_2"
    Set tC = New cTeam
    tC.Team_ID = "D2_Team_C"
    tC.Department_ID = "Dept_2"
    tC.FTE_Count = 10
    d2.Teams.Add tC
    d2.RefreshTotalFTE
    col.Add d2

    Set d3 = New cDepartment
    d3.Dept_ID = "Dept_3"
    Set tD = New cTeam
    tD.Team_ID = "D3_Team_D"
    tD.Department_ID = "Dept_3"
    tD.FTE_Count = 10
    d3.Teams.Add tD
    d3.RefreshTotalFTE
    col.Add d3

    Set BuildTestDepartments = col
End Function

''' Edge case: Req=45 at 08:00 → Dept1 capped at 20 (A=18,B=2), shortfall logged.
Private Sub Run_CapHit_EdgeCase()
    On Error GoTo ErrHandler

    Dim depts As Collection
    Dim req As Object
    Dim opt As cPhoneScheduleOptimizer
    Dim i As Long
    Dim arr509(1 To 24) As Long
    Dim arr518(1 To 24) As Long

    Set depts = BuildTestDepartments()
    Set req = CreateObject("Scripting.Dictionary")

    arr509(1) = 45
    For i = 2 To 24
        arr509(i) = 0
    Next i
    For i = 1 To 24
        arr518(i) = 0
    Next i

    req.Add "App_509", arr509
    req.Add "App_518", arr518

    Set opt = New cPhoneScheduleOptimizer
    opt.Initialize depts, req
    opt.GenerateSchedule

    Dim a As Long, b As Long
    a = opt.GetAllocation("App_509", 1, "D1_Team_A")
    b = opt.GetAllocation("App_509", 1, "D1_Team_B")

    Debug.Print "CapHit Slot1 -> A=" & a & " B=" & b & " (expect 18, 2)"
    Debug.Assert a = 18
    Debug.Assert b = 2

    If a <> 18 Or b <> 2 Then
        MsgBox "CAP EDGE FAIL: Expected A=18 B=2. Got A=" & a & " B=" & b, vbCritical
    Else
        Debug.Print "Cap-hit edge case PASSED"
    End If
    Exit Sub

ErrHandler:
    MsgBox "Run_CapHit_EdgeCase ERROR " & Err.Number & ": " & Err.Description, vbCritical
End Sub

'-------------------------------------------------------------------------------
' PRODUCTION ENTRY
' Expects optional sheets:
'   Config_Teams: Team_ID | Department_ID | FTE_Count
'   Config_Requirements: Time | App_509 | App_518  (24 rows 08:00..19:30)
' If missing, falls back to Run_Test_Case data structure message.
'-------------------------------------------------------------------------------
Public Sub Run_Production()
    On Error GoTo ErrHandler

    Dim wsTeams As Worksheet
    Dim wsReq As Worksheet

    On Error Resume Next
    Set wsTeams = ThisWorkbook.Worksheets("Config_Teams")
    Set wsReq = ThisWorkbook.Worksheets("Config_Requirements")
    On Error GoTo ErrHandler

    If wsTeams Is Nothing Or wsReq Is Nothing Then
        MsgBox "Config_Teams / Config_Requirements sheets not found." & vbCrLf & _
               "Running built-in test case instead. Create those sheets for production input.", _
               vbExclamation
        Call Run_Test_Case
        Exit Sub
    End If

    Dim depts As Collection
    Dim req As Object
    Dim opt As cPhoneScheduleOptimizer

    Set depts = LoadDepartmentsFromSheet(wsTeams)
    Set req = LoadRequirementsFromSheet(wsReq)

    Set opt = New cPhoneScheduleOptimizer
    opt.Initialize depts, req
    If Not opt.GenerateSchedule() Then
        MsgBox "GenerateSchedule failed", vbCritical
        Exit Sub
    End If
    opt.ExportToSheets ThisWorkbook
    opt.PrintFairnessSummary
    MsgBox "Production schedule generated.", vbInformation
    Exit Sub

ErrHandler:
    MsgBox "Run_Production ERROR " & Err.Number & ": " & Err.Description, vbCritical
End Sub

Private Function LoadDepartmentsFromSheet(ws As Worksheet) As Collection
    Dim col As Collection
    Dim deptMap As Object
    Dim lastRow As Long
    Dim r As Long
    Dim teamID As String, deptID As String
    Dim fte As Long
    Dim d As cDepartment
    Dim t As cTeam
    Dim key As Variant

    Set col = New Collection
    Set deptMap = CreateObject("Scripting.Dictionary")

    lastRow = ws.Cells(ws.Rows.Count, 1).End(xlUp).Row
    ' Assume header row 1: Team_ID | Department_ID | FTE_Count
    For r = 2 To lastRow
        teamID = Trim$(CStr(ws.Cells(r, 1).Value))
        deptID = Trim$(CStr(ws.Cells(r, 2).Value))
        fte = CLng(ws.Cells(r, 3).Value)
        If Len(teamID) = 0 Or Len(deptID) = 0 Then GoTo NextRow

        If Not deptMap.Exists(deptID) Then
            Set d = New cDepartment
            d.Dept_ID = deptID
            deptMap.Add deptID, d
        Else
            Set d = deptMap(deptID)
        End If

        Set t = New cTeam
        t.Team_ID = teamID
        t.Department_ID = deptID
        t.FTE_Count = fte
        d.Teams.Add t
NextRow:
    Next r

    For Each key In deptMap.Keys
        Set d = deptMap(key)
        d.RefreshTotalFTE
        col.Add d
    Next key

    Set LoadDepartmentsFromSheet = col
End Function

Private Function LoadRequirementsFromSheet(ws As Worksheet) As Object
    Dim dict As Object
    Dim arr509(1 To 24) As Long
    Dim arr518(1 To 24) As Long
    Dim r As Long
    Dim i As Long

    Set dict = CreateObject("Scripting.Dictionary")
    ' Header row 1: Time | App_509 | App_518 ; data rows 2..25
    For i = 1 To 24
        r = i + 1
        arr509(i) = CLng(Val(ws.Cells(r, 2).Value))
        arr518(i) = CLng(Val(ws.Cells(r, 3).Value))
    Next i
    dict.Add "App_509", arr509
    dict.Add "App_518", arr518
    Set LoadRequirementsFromSheet = dict
End Function
