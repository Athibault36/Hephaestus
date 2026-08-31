VERSION 1.0 CLASS
BEGIN
  MultiUse = -1  'True
END
Attribute VB_Name = "cDepartment"
Attribute VB_GlobalNameSpace = False
Attribute VB_Creatable = False
Attribute VB_PredeclaredId = False
Attribute VB_Exposed = False
'===============================================================================
' cDepartment.cls
' Department entity containing a collection of cTeam objects.
'===============================================================================
Option Explicit

Public Dept_ID As String
Public Teams As Collection        ' Collection of cTeam objects
Public Total_FTE As Long          ' Sum of Team.FTE_Count
Public Weight As Double           ' Calculated: Total_FTE / Global_Total_FTE

Private Sub Class_Initialize()
    Set Teams = New Collection
End Sub

Private Sub Class_Terminate()
    Set Teams = Nothing
End Sub

''' Recalculate Total_FTE from member teams.
Public Sub RefreshTotalFTE()
    Dim t As cTeam
    Dim sumFTE As Long
    sumFTE = 0
    If Not Teams Is Nothing Then
        For Each t In Teams
            sumFTE = sumFTE + t.FTE_Count
        Next t
    End If
    Total_FTE = sumFTE
End Sub
