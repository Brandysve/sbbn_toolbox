using System;
using System.Diagnostics;
using System.IO;
using System.Linq;
using System.Reflection;

[assembly: AssemblyTitle("SBBN Toolbox")]
[assembly: AssemblyProduct("SBBN Toolbox")]
[assembly: AssemblyDescription("Lanceur portable SBBN Toolbox")]
[assembly: AssemblyCompany("SBBN")]
[assembly: AssemblyVersion("1.0.0.0")]
[assembly: AssemblyFileVersion("1.0.0.0")]

internal static class PortableLauncher
{
    [STAThread]
    private static int Main(string[] args)
    {
        string root = AppDomain.CurrentDomain.BaseDirectory;
        string executable = Path.Combine(root, "runtime", "SBBN-Toolbox-runtime.exe");
        if (!File.Exists(executable))
        {
            return 2;
        }

        var startInfo = new ProcessStartInfo
        {
            FileName = executable,
            WorkingDirectory = root,
            UseShellExecute = false,
            CreateNoWindow = true,
            Arguments = string.Join(" ", args.Select(QuoteArgument))
        };
        using (Process process = Process.Start(startInfo))
        {
            process.WaitForExit();
            return process.ExitCode;
        }
    }

    private static string QuoteArgument(string argument)
    {
        return "\"" + argument.Replace("\\", "\\\\").Replace("\"", "\\\"") + "\"";
    }
}
