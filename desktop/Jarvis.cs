using System;
using System.Diagnostics;
using System.Drawing;
using System.IO;
using System.Reflection;
using System.Runtime.InteropServices;
using System.Threading;
using System.Threading.Tasks;
using System.Windows.Forms;
using Microsoft.Web.WebView2.Core;
using Microsoft.Web.WebView2.WinForms;

[assembly: AssemblyTitle("Personal Jarvis")]
[assembly: AssemblyDescription("Local voice assistant for Windows")]
[assembly: AssemblyCompany("Sannith Vanamala")]
[assembly: AssemblyProduct("Personal Jarvis")]
[assembly: AssemblyVersion("0.2.0.0")]
[assembly: AssemblyFileVersion("0.2.0.0")]
internal static class Program {
    internal const string AppId = "Sannith.PersonalJarvis";
    internal static string Root = Path.GetFullPath(Path.Combine(AppDomain.CurrentDomain.BaseDirectory, "..", ".."));
    [DllImport("shell32.dll")] private static extern int SetCurrentProcessExplicitAppUserModelID([MarshalAs(UnmanagedType.LPWStr)] string id);
    [DllImport("user32.dll")] private static extern bool SetProcessDPIAware();
    [DllImport("user32.dll", CharSet=CharSet.Unicode)] private static extern IntPtr FindWindow(string cls, string title);
    [DllImport("user32.dll")] private static extern bool SetForegroundWindow(IntPtr window);
    [DllImport("user32.dll")] private static extern bool ShowWindow(IntPtr window, int command);
    [STAThread] static void Main(string[] args) {
        SetCurrentProcessExplicitAppUserModelID(AppId);
        SetProcessDPIAware();
        bool created;
        using (var mutex = new Mutex(true, @"Local\PersonalJarvis.Desktop", out created)) {
            if (!created) { var window=FindWindow(null,"Jarvis"); if(window!=IntPtr.Zero){ShowWindow(window,9);SetForegroundWindow(window);} return; }
            try {
                // The kernel tears down services and model runners even after a crash.
                NativeJob.OwnCurrentProcess();
                Application.EnableVisualStyles();
                Application.SetCompatibleTextRenderingDefault(false);
                Application.Run(new JarvisWindow(Array.IndexOf(args,"--test")>=0));
            } catch(Exception error) {
                Directory.CreateDirectory(Path.Combine(Root,"data"));
                File.AppendAllText(Path.Combine(Root,"data","desktop.log"), DateTime.Now+" "+error+Environment.NewLine);
                MessageBox.Show("Jarvis could not start. Run Setup Jarvis, or check data/desktop.log.\n\n"+error.Message,"Jarvis",MessageBoxButtons.OK,MessageBoxIcon.Error);
            }
            GC.KeepAlive(NativeJob.Handle);
        }
    }
}
internal sealed class JarvisWindow : Form {
    private WebView2 view;
    private readonly bool test;
    private readonly Label note = new Label();
    private bool closing;
    public JarvisWindow(bool testMode) {
        test=testMode; Text="Jarvis"; BackColor=Color.FromArgb(17,22,21);
        Icon=new Icon(Path.Combine(Program.Root,"web","assets","jarvis.ico"));
        StartPosition=FormStartPosition.CenterScreen;AutoScaleMode=AutoScaleMode.Dpi;
        Size=new Size(Math.Min(1400,Screen.PrimaryScreen.WorkingArea.Width),Math.Min(960,Screen.PrimaryScreen.WorkingArea.Height));
        MinimumSize=new Size(900,620);
        note.Dock=DockStyle.Fill;note.TextAlign=ContentAlignment.MiddleCenter;
        note.ForeColor=Color.FromArgb(227,212,158);note.Font=new Font("Segoe UI",15);
        note.Text="JARVIS\n\nPreparing your local workspace.";
        Controls.Add(note);
        Shown+=async delegate { await Start(); };
        FormClosing+=delegate { closing=true; };
        FormClosed+=delegate {
            if(view!=null)view.Dispose();
            try { RunScript("stop.ps1","-ServicesOnly",6000); } catch { }
        };
    }
    private static void RunScript(string file,string extra,int timeout) {
        var info=new ProcessStartInfo("powershell.exe","-NoProfile -NonInteractive -ExecutionPolicy Bypass -File \""+
            Path.Combine(Program.Root,"scripts",file)+"\" "+extra);
        info.WorkingDirectory=Program.Root;info.UseShellExecute=false;info.CreateNoWindow=true;
        using(var process=Process.Start(info)) {
            if(!process.WaitForExit(timeout))throw new TimeoutException("Service startup timed out");
            if(process.ExitCode!=0)throw new Exception(file+" failed. Check the local logs.");
        }
    }
    private async Task Start() {
        try {
            await Task.Run(delegate { RunScript("stop.ps1","-ServicesOnly",10000); RunScript("launch.ps1","-NoWindow",40000); });
            if(closing)return;
            view=new WebView2();view.Dock=DockStyle.Fill;view.DefaultBackgroundColor=BackColor;
            Controls.Add(view);view.BringToFront();
            var options=new CoreWebView2EnvironmentOptions("--autoplay-policy=no-user-gesture-required"+(test?" --remote-debugging-port=9223":""));
            var environment=await CoreWebView2Environment.CreateAsync(null,Path.Combine(Program.Root,"data","webview"),options);
            if(closing)return;
            await view.EnsureCoreWebView2Async(environment);
            view.CoreWebView2.Settings.IsStatusBarEnabled=false;
            view.CoreWebView2.Settings.AreDevToolsEnabled=test;
            view.CoreWebView2.PermissionRequested+=delegate(object sender,CoreWebView2PermissionRequestedEventArgs e) {
                Uri uri;
                bool local=Uri.TryCreate(e.Uri,UriKind.Absolute,out uri)&&uri.Scheme=="http"&&uri.Host=="127.0.0.1"&&uri.Port==8765;
                if(e.PermissionKind==CoreWebView2PermissionKind.Microphone) {
                    e.State=local?CoreWebView2PermissionState.Allow:CoreWebView2PermissionState.Deny;
                    e.SavesInProfile=false;
                }
            };
            view.CoreWebView2.NewWindowRequested+=delegate(object sender,CoreWebView2NewWindowRequestedEventArgs e){e.Handled=true;OpenExternal(e.Uri);};
            view.CoreWebView2.NavigationStarting+=delegate(object sender,CoreWebView2NavigationStartingEventArgs e){
                Uri uri;
                if(!Uri.TryCreate(e.Uri,UriKind.Absolute,out uri)||uri.Scheme!="http"||uri.Host!="127.0.0.1"||uri.Port!=8765){
                    e.Cancel=true;OpenExternal(e.Uri);
                }
            };
            view.CoreWebView2.ProcessFailed+=delegate{if(!closing){MessageBox.Show("The voice window stopped. Please reopen Jarvis.","Jarvis");Close();}};
            view.Source=new Uri("http://127.0.0.1:8765");Controls.Remove(note);note.Dispose();
        } catch(Exception error) {
            if(closing)return;
            note.Text="Jarvis needs a moment of maintenance.\n\n"+error.Message+"\n\nRun Setup Jarvis, then reopen.";
            Directory.CreateDirectory(Path.Combine(Program.Root,"data"));
            File.AppendAllText(Path.Combine(Program.Root,"data","desktop.log"),DateTime.Now+" "+error+Environment.NewLine);
        }
    }
    private static void OpenExternal(string value) {
        Uri uri;
        if(Uri.TryCreate(value,UriKind.Absolute,out uri)&&(uri.Scheme=="http"||uri.Scheme=="https"))
            Process.Start(new ProcessStartInfo(value){UseShellExecute=true});
    }
}
internal static class NativeJob {
    internal static IntPtr Handle;
    [StructLayout(LayoutKind.Sequential)] struct Basic { public long ProcessTime,JobTime;public uint Flags;public UIntPtr Min,Max;public uint Processes;public UIntPtr Affinity;public uint Priority,Scheduling; }
    [StructLayout(LayoutKind.Sequential)] struct Counters { public ulong A,B,C,D,E,F; }
    [StructLayout(LayoutKind.Sequential)] struct Limits { public Basic Basic;public Counters IO;public UIntPtr ProcessMemory,JobMemory,PeakProcess,PeakJob; }
    [DllImport("kernel32.dll",CharSet=CharSet.Unicode,SetLastError=true)] static extern IntPtr CreateJobObject(IntPtr security,string name);
    [DllImport("kernel32.dll",SetLastError=true)] static extern bool SetInformationJobObject(IntPtr job,int kind,ref Limits limits,uint length);
    [DllImport("kernel32.dll",SetLastError=true)] static extern bool AssignProcessToJobObject(IntPtr job,IntPtr process);
    internal static void OwnCurrentProcess() {
        Handle=CreateJobObject(IntPtr.Zero,null);
        var limits=new Limits();limits.Basic.Flags=0x2000|0x0800; // Kill on close; allow explicit user-app breakaway.
        if(Handle==IntPtr.Zero||!SetInformationJobObject(Handle,9,ref limits,(uint)Marshal.SizeOf(limits))||
           !AssignProcessToJobObject(Handle,Process.GetCurrentProcess().Handle))
            throw new System.ComponentModel.Win32Exception(Marshal.GetLastWin32Error(),"Could not own local services");
    }
}
