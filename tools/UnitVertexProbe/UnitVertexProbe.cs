using System;
using System.Collections;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Reflection;
using System.Runtime.InteropServices;
using System.Security.Cryptography;
using System.Text;

internal static class UnitVertexProbe
{
    private const string Sdk = @"C:\Program Files (x86)\Steam\steamapps\common\Sid Meier's Civilization V SDK\Nexus\x86";
    private const string Pipeline = @"C:\Users\home\OneDrive\Documents\Firaxis ModBuddy\ZeroSis' Daelaam Protoss\Tools\ArchonPipeline";
    private static Assembly Bridge;

    [DllImport("kernel32.dll", CharSet = CharSet.Unicode)] private static extern bool SetDllDirectory(string path);
    [DllImport("kernel32.dll")] private static extern uint SetErrorMode(uint mode);
    private const uint SemFailCriticalErrors = 0x0001, SemNoGpFaultErrorBox = 0x0002;

    private static Assembly Resolve(object sender, ResolveEventArgs e)
    {
        string name = new AssemblyName(e.Name).Name;
        string privatePath = Path.Combine(AppDomain.CurrentDomain.BaseDirectory, name + ".dll");
        string sdkPath = Path.Combine(Sdk, name + ".dll");
        string toolPath = Path.Combine(Pipeline, name + ".dll");
        if (File.Exists(privatePath)) return Assembly.LoadFrom(privatePath);
        if (File.Exists(sdkPath)) return Assembly.LoadFrom(sdkPath);
        if (File.Exists(toolPath)) return Assembly.LoadFrom(toolPath);
        return null;
    }

    private static Type FindType(string name)
    {
        foreach (Assembly a in AppDomain.CurrentDomain.GetAssemblies())
        {
            Type t = a.GetType(name, false);
            if (t != null) return t;
        }
        foreach (string file in new[] { "Firaxis.Framework.dll", "Firaxis.Framework.Granny.dll", "Firaxis.Framework.FirePlace.dll" })
        {
            string privatePath = Path.Combine(AppDomain.CurrentDomain.BaseDirectory, file);
            if (File.Exists(privatePath))
            {
                Type t = Assembly.LoadFrom(privatePath).GetType(name, false);
                if (t != null) return t;
            }
            string path = Path.Combine(Sdk, file);
            if (File.Exists(path))
            {
                Type t = Assembly.LoadFrom(path).GetType(name, false);
                if (t != null) return t;
            }
        }
        return null;
    }

    private static object Construct(string fullName)
    {
        Type t = FindType(fullName);
        if (t == null) throw new InvalidOperationException("Type not found: " + fullName);
        return Activator.CreateInstance(t);
    }

    private static void AddToSdkContext(object value)
    {
        Type context = FindType("Firaxis.Framework.Context");
        if (context == null) throw new InvalidOperationException("SDK Context type not found");
        MethodInfo add = context.GetMethods(BindingFlags.Public | BindingFlags.Static)
            .FirstOrDefault(m => m.Name == "Add" && m.GetParameters().Length == 1 && m.GetParameters()[0].ParameterType.IsAssignableFrom(value.GetType()));
        if (add == null) throw new InvalidOperationException("SDK Context.Add overload not found for " + value.GetType().FullName);
        add.Invoke(null, new[] { value });
    }

    private static string Escape(string s) { return s.Replace("\\", "\\\\").Replace("\"", "\\\"").Replace("\r", "\\r").Replace("\n", "\\n"); }
    private static string Hash(string path)
    {
        using (SHA256 h = SHA256.Create())
        using (FileStream f = File.OpenRead(path)) return BitConverter.ToString(h.ComputeHash(f)).Replace("-", "").ToLowerInvariant();
    }

    private static int Main(string[] args)
    {
        try { return Run(args); }
        catch (Exception ex)
        {
            Exception root = ex;
            while (root.InnerException != null) root = root.InnerException;
            string diagnostic = "ERROR_TYPE=" + ex.GetType().FullName + Environment.NewLine +
                "ERROR_MESSAGE=" + ex.Message + Environment.NewLine +
                "ROOT_TYPE=" + root.GetType().FullName + Environment.NewLine +
                "ROOT_MESSAGE=" + root.Message + Environment.NewLine +
                "ROOT_FILE=" + (root is FileNotFoundException ? ((FileNotFoundException)root).FileName : "") + Environment.NewLine +
                "ROOT_STACK=" + root.StackTrace + Environment.NewLine +
                "HResult=0x" + ex.HResult.ToString("X8") + Environment.NewLine;
            if (args.Length > 1)
            {
                try { File.WriteAllText(Path.GetFullPath(args[1]) + ".error.txt", diagnostic, new UTF8Encoding(false)); }
                catch { }
            }
            Console.Error.WriteLine(diagnostic);
            return 1;
        }
    }

    private static int Run(string[] args)
    {
        SetErrorMode(SemFailCriticalErrors | SemNoGpFaultErrorBox);
        SetDllDirectory(Sdk);
        Directory.SetCurrentDirectory(Sdk);
        AppDomain.CurrentDomain.AssemblyResolve += Resolve;
        Bridge = Assembly.LoadFrom(Path.Combine(AppDomain.CurrentDomain.BaseDirectory, "GrannyBridge.exe"));
        if (args.Length != 3) { Console.Error.WriteLine("usage: UnitVertexProbe.exe <source.gr2> <report.json> <copy-dir>"); return 2; }
        string input = Path.GetFullPath(args[0]), report = Path.GetFullPath(args[1]), copyDir = Path.GetFullPath(args[2]);
        if (!File.Exists(input) || new FileInfo(input).Length > 64 * 1024 * 1024) throw new InvalidDataException("Input absent or exceeds 64 MiB bound");
        Directory.CreateDirectory(copyDir);
        string privateCopy = Path.Combine(copyDir, Path.GetFileName(input));
        File.Copy(input, privateCopy, true);
        try
        {
            object virtualSpace = Construct("Firaxis.Framework.VirtualSpace");
            virtualSpace.GetType().GetProperty("BasePaths").SetValue(virtualSpace, new List<string>(), null);
            AddToSdkContext(virtualSpace);
            AddToSdkContext(Construct("Firaxis.Framework.ProjectConfig"));
            object grannyContext = Construct("Firaxis.Framework.Granny.GrannyContext");
            AddToSdkContext(grannyContext);
            Type formType = Bridge.GetType("NexusBuddy.NexusBuddyApplicationForm", true);
            ConstructorInfo formCtor = formType.GetConstructor(new[] { grannyContext.GetType() });
            if (formCtor == null) throw new InvalidOperationException("NexusBuddy form bootstrap constructor not found");
            formType.GetField("form", BindingFlags.Public | BindingFlags.Static).SetValue(null, formCtor.Invoke(new[] { grannyContext }));
            object grannyFile = grannyContext.GetType().GetMethod("LoadGrannyFile").Invoke(grannyContext, new object[] { privateCopy });
            IEnumerable meshes = (IEnumerable)grannyFile.GetType().GetProperty("Meshes").GetValue(grannyFile, null);
            Type wrapperType = Bridge.GetType("NexusBuddy.GrannyWrappers.GrannyMeshWrapper", true);
            MethodInfo getLayout = wrapperType.GetMethod("getVertexStructInfos", BindingFlags.NonPublic | BindingFlags.Instance);
            if (getLayout == null) throw new InvalidOperationException("Existing GrannyMeshWrapper private vertex descriptor method not found");
            StringBuilder json = new StringBuilder();
            json.Append("{\"source\":\"").Append(Escape(input)).Append("\",\"private_copy\":\"").Append(Escape(privateCopy))
                .Append("\",\"source_sha256\":\"").Append(Hash(input)).Append("\",\"private_copy_sha256\":\"").Append(Hash(privateCopy)).Append("\",\"meshes\":[");
            bool firstMesh = true;
            foreach (object mesh in meshes)
            {
                if (!firstMesh) json.Append(','); firstMesh = false;
                object wrapper = Activator.CreateInstance(wrapperType, new[] { mesh });
                IList layout = (IList)getLayout.Invoke(wrapper, null);
                int offset = 0;
                json.Append("{\"name\":\"").Append(Escape(Convert.ToString(mesh.GetType().GetProperty("Name").GetValue(mesh, null))))
                    .Append("\",\"vertex_count\":").Append(Convert.ToInt32(mesh.GetType().GetProperty("VertexCount").GetValue(mesh, null)))
                    .Append(",\"attributes\":[");
                for (int i = 0; i < layout.Count; i++)
                {
                    if (i != 0) json.Append(',');
                    object attr = layout[i]; Type at = attr.GetType();
                    string name = Convert.ToString(at.GetField("name").GetValue(attr));
                    int type = Convert.ToInt32(at.GetField("type").GetValue(attr));
                    int count = Convert.ToInt32(at.GetField("count").GetValue(attr));
                    int length = Convert.ToInt32(at.GetField("length").GetValue(attr));
                    json.Append("{\"name\":\"").Append(Escape(name)).Append("\",\"type\":").Append(type)
                        .Append(",\"count\":").Append(count).Append(",\"element_bytes\":").Append(length).Append(",\"offset\":").Append(offset).Append('}');
                    if (count < 0 || count > 64 || length < 0 || length > 8 || offset > 4096) throw new InvalidDataException("SDK descriptor exceeds layout bounds");
                    offset = checked(offset + count * length);
                }
                json.Append("],\"bytes_per_vertex\":").Append(offset).Append('}');
                if (offset <= 0 || offset > 4096) throw new InvalidDataException("SDK vertex stride outside 1..4096 bytes");
            }
            json.Append("]}");
            File.WriteAllText(report, json.ToString(), new UTF8Encoding(false));
            Console.WriteLine("VERTEX_LAYOUT_REPORT=" + report);
            Console.WriteLine("SOURCE_SHA256=" + Hash(input));
            return 0;
        }
        finally { /* Preserve the private copy and source report inputs for provenance. */ }
    }
}

