VERSION 1.0 CLASS
BEGIN
  MultiUse = -1  'True
END
Attribute VB_Name = "cTeam"
Attribute VB_GlobalNameSpace = False
Attribute VB_Creatable = False
Attribute VB_PredeclaredId = False
Attribute VB_Exposed = False
'===============================================================================
' cTeam.cls
' Team entity for proportional phone line staffing.
'===============================================================================
Option Explicit

Public Team_ID As String          ' e.g., "D1_Team_A"
Public Department_ID As String    ' e.g., "Dept_1"
Public FTE_Count As Long          ' Max capacity per half-hour (Integer > 0)
Public Weight As Double           ' Calculated: FTE_Count / Dept_Total_FTE
