// Bounded x64 check of the SDK's public animation-curve sampler.
// This probe deliberately does not call IGrannyAnimation.SampleBone.
using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Linq;
using System.Reflection;
using System.Runtime.CompilerServices;
using System.Runtime.InteropServices;
using System.Security.Cryptography;
using System.Text;
using System.Web.Script.Serialization;
using Firaxis.Framework;
using Firaxis.Framework.Granny;

internal static class GrannyAnimationProbe
{
    private static string Sdk;
    private static readonly List<object> LoadedAssemblies = new List<object>();
    private static readonly List<string> AssemblyResolveLog = new List<string>();

    [DllImport("kernel32.dll", CharSet = CharSet.Unicode)]
    private static extern bool SetDllDirectory(string path);
    [DllImport("kernel32.dll")]
    private static extern uint SetErrorMode(uint mode);
    [DllImport("wer.dll")]
    private static extern int WerSetFlags(uint flags);

    private static void Require(bool ok, string message)
    {
        if (!ok) throw new InvalidDataException(message);
    }

    private static Dictionary<string, object> Object(object value, string label)
    {
        var result = value as Dictionary<string, object>;
        Require(result != null, label + " is not an object");
        return result;
    }

    private static object[] Array(object value, string label)
    {
        var result = value as object[];
        Require(result != null, label + " is not an array");
        return result;
    }

    private static string GetString(Dictionary<string, object> row, string name)
    {
        object value;
        Require(row.TryGetValue(name, out value) && value is string, "Missing string " + name);
        return (string)value;
    }

    private static double Number(object value, string label)
    {
        Require(value is int || value is long || value is float || value is double || value is decimal,
                label + " is not numeric");
        double result = Convert.ToDouble(value, CultureInfo.InvariantCulture);
        Require(!Double.IsNaN(result) && !Double.IsInfinity(result), label + " is nonfinite");
        return result;
    }

    private static double[] Numbers(object value, int expected, string label)
    {
        object[] raw = Array(value, label);
        Require(raw.Length == expected, label + " dimension mismatch");
        return raw.Select((v, i) => Number(v, label + "[" + i + "]")).ToArray();
    }

    private static string Hash(byte[] value)
    {
        using (SHA256 sha = SHA256.Create())
            return BitConverter.ToString(sha.ComputeHash(value)).Replace("-", "").ToLowerInvariant();
    }

    private static float[] Sample(IGrannyCurve curve, float time, float duration, bool normalize)
    {
        Require(curve != null, "Missing original transform curve");
        float[] result = curve.Sample(time, duration, normalize, false, false);
        Require(result != null && result.Length == curve.Dimension, "Curve.Sample returned wrong dimension");
        Require(result.All(v => !Single.IsNaN(v) && !Single.IsInfinity(v)), "Curve.Sample returned nonfinite data");
        return result;
    }

    private static string CurveName(string track, string channel)
    {
        return track + "\u001f" + channel;
    }

    private static float[] CurveValue(IGrannyTransformTrack track, string channel, float time, float duration)
    {
        if (channel == "position") return Sample(track.PositionCurve, time, duration, false);
        if (channel == "orientation") return Sample(track.OrientationCurve, time, duration, true);
        return Sample(track.ScaleShearCurve, time, duration, false);
    }

    private static int Run(string[] args)
    {
        Require(args.Length == 4, "usage: GrannyAnimationProbe <sdk-dir> <names.gsd> <model.gr2> <idle.gr2>");
        string gsd = Path.GetFullPath(args[1]);
        string modelPath = Path.GetFullPath(args[2]);
        string animationPath = Path.GetFullPath(args[3]);
        // Remaining two paths are supplied as environment variables so that the
        // public SDK boundary stays limited to the four native inputs.
        string expectedPath = Environment.GetEnvironmentVariable("ZS_GRANNY_EXPECTED_JSON");
        string outputPath = Environment.GetEnvironmentVariable("ZS_GRANNY_OUTPUT_JSON");
        Require(!String.IsNullOrWhiteSpace(expectedPath) && !String.IsNullOrWhiteSpace(outputPath),
                "Expected export/output paths were not provided");
        expectedPath = Path.GetFullPath(expectedPath);
        outputPath = Path.GetFullPath(outputPath);
        Require(File.Exists(gsd) && File.Exists(modelPath) && File.Exists(animationPath) && File.Exists(expectedPath),
                "A bounded probe input is missing");
        Require(Environment.Is64BitProcess && IntPtr.Size == 8, "Probe is not running as x64");

        Console.WriteLine("LOAD_STRING_DATABASE=" + gsd);

        VirtualSpace space = new VirtualSpace();
        space.BasePaths = new List<string>();
        Context.Add(space);
        Context.Add(new ProjectConfig());
        GrannyContext context = new GrannyContext();
        Context.Add(context);
        context.LoadStringDatabase(gsd);
        IGrannyFile modelFile = context.LoadGrannyFile(modelPath);
        Require(modelFile != null && modelFile.Models.Count == 1 && modelFile.Models[0].Skeleton != null,
                "Expected one original Warrior model");
        IGrannyModel model = modelFile.Models[0];
        IGrannyFile animationFile = context.LoadGrannyFile(animationPath);
        Require(animationFile != null && animationFile.Animations.Count == 1,
                "Expected one original idle animation");
        IGrannyAnimation animation = animationFile.Animations[0];
        Require(animation.Duration > 0 && !Single.IsNaN(animation.Duration) && !Single.IsInfinity(animation.Duration),
                "Invalid source animation duration");

        var expectedSerializer = new JavaScriptSerializer();
        expectedSerializer.MaxJsonLength = 4 * 1024 * 1024;
        var expected = Object(expectedSerializer.DeserializeObject(File.ReadAllText(expectedPath, Encoding.UTF8)), "x86 t0 export");
        var expectedModels = Array(expected["models"], "models");
        Require(expectedModels.Length == 1, "x86 export model count mismatch");
        string expectedModelName = GetString(Object(expectedModels[0], "model"), "name");
        Require(model.Name == expectedModelName, "x64 model identity differs from x86 export");
        var expectedPose = Object(expected["pose"], "pose");
        double expectedDuration = Number(expectedPose["duration"], "x86 duration");
        Require(Math.Abs(animation.Duration - expectedDuration) < 1e-4, "x64 animation duration differs from x86 export");
        var expectedTrackRows = Array(expectedPose["sampled_tracks"], "x86 sampled tracks");
        var expectedTracks = expectedTrackRows.Select(v => Object(v, "x86 track"))
            .ToDictionary(row => GetString(row, "name"), StringComparer.Ordinal);

        var groups = animation.TrackGroups.Where(g => g.Name == model.Name).ToArray();
        Require(groups.Length == 1, "Original animation has no unique model-matched track group");
        var tracks = groups[0].TransformTracks;
        Require(tracks.Count == expectedTracks.Count && tracks.Count > 0 &&
                tracks.Select(t => t.Name).Distinct().Count() == tracks.Count,
                "x64 track set differs from x86 t0 export");
        string backendName = Path.GetFileName(animation.GetType().Assembly.Location);
        string curveBackendName = Path.GetFileName(tracks[0].PositionCurve.GetType().Assembly.Location);
        Require(String.Equals(backendName, "Firaxis.Framework.Granny.Implx64.dll", StringComparison.OrdinalIgnoreCase) &&
                String.Equals(curveBackendName, "Firaxis.Framework.Granny.Implx64.dll", StringComparison.OrdinalIgnoreCase),
                "GrannyContext did not select the installed x64 curve/animation implementation");

        float duration = animation.Duration;
        float[] times = new float[] { 0f, 0.5f, 1f, duration * 0.5f, duration };
        Require(times.All(t => t >= 0 && t <= duration), "Requested sample time outside source animation");
        string[] channels = new string[] { "position", "orientation", "scale_shear" };
        var samples = new Dictionary<string, float[][]>();
        double maxT0Error = 0;
        int comparedComponents = 0;
        foreach (var track in tracks)
        {
            Dictionary<string, object> old;
            Require(expectedTracks.TryGetValue(track.Name, out old), "x64 animation track missing from x86 export: " + track.Name);
            foreach (string channel in channels)
            {
                int dimension = channel == "position" ? 3 : channel == "orientation" ? 4 : 9;
                double[] oldValues = Numbers(old[channel], dimension, "x86 " + channel);
                float[] now = Sample(track.PositionCurve == null && channel == "position" ? null :
                    channel == "position" ? track.PositionCurve : channel == "orientation" ? track.OrientationCurve : track.ScaleShearCurve,
                    0f, duration, channel == "orientation");
                Require(now.Length == dimension, "x86/x64 curve dimension mismatch");
                for (int i = 0; i < dimension; ++i)
                {
                    maxT0Error = Math.Max(maxT0Error, Math.Abs(now[i] - oldValues[i]));
                    ++comparedComponents;
                }
                samples.Add(CurveName(track.Name, channel), new float[times.Length][]);
            }
        }

        // Evaluate each original curve through the public SDK API at bounded times.
        for (int ti = 0; ti < times.Length; ++ti)
            foreach (var track in tracks)
                foreach (string channel in channels)
                    samples[CurveName(track.Name, channel)][ti] = CurveValue(track, channel, times[ti], duration);
        Require(maxT0Error < 1e-5, "x64 t0 public curve samples differ from established x86 t0 export");

        var sampleSummaries = new List<object>();
        string dynamicCurve = null;
        double largestDelta = 0;
        foreach (var track in tracks)
            foreach (string channel in channels)
            {
                string name = CurveName(track.Name, channel);
                float[][] values = samples[name];
                for (int ti = 1; ti < times.Length; ++ti)
                    for (int j = 0; j < values[ti].Length; ++j)
                    {
                        double delta = Math.Abs(values[ti][j] - values[0][j]);
                        if (delta > largestDelta) { largestDelta = delta; dynamicCurve = name; }
                    }
            }
        for (int ti = 0; ti < times.Length; ++ti)
        {
            using (var bytes = new MemoryStream())
            using (var writer = new BinaryWriter(bytes, Encoding.UTF8, true))
            {
                int changedCurves = 0;
                double maxDelta = 0;
                foreach (var track in tracks)
                    foreach (string channel in channels)
                    {
                        string key = CurveName(track.Name, channel);
                        float[] value = samples[key][ti];
                        writer.Write(key);
                        bool changed = false;
                        for (int j = 0; j < value.Length; ++j)
                        {
                            writer.Write(value[j]);
                            double delta = Math.Abs(value[j] - samples[key][0][j]);
                            maxDelta = Math.Max(maxDelta, delta);
                            changed |= delta > 1e-6;
                        }
                        if (changed) ++changedCurves;
                    }
                writer.Flush();
                sampleSummaries.Add(new { time = times[ti], curves = tracks.Count * channels.Length,
                    finite = true, changed_curves_vs_t0 = changedCurves,
                    max_abs_delta_vs_t0 = maxDelta, sha256 = Hash(bytes.ToArray()) });
            }
        }
        Require(dynamicCurve != null && largestDelta > 1e-6,
                "The original curve values did not change over the sampled interval");
        var dynamicSummary = (object)null;
        if (dynamicCurve != null)
        {
            string[] parts = dynamicCurve.Split('\u001f');
            float[][] values = samples[dynamicCurve];
            dynamicSummary = new { bone = parts[0], channel = parts[1], max_abs_delta = largestDelta,
                                   samples = times.Select((t, i) => new { time = t, values = values[i] }).ToArray() };
        }

        var info = new { status = "PASS_PUBLIC_CURVE_SAMPLE_X64", process = new { is_64_bit = Environment.Is64BitProcess,
            pointer_bytes = IntPtr.Size, clr_version = Environment.Version.ToString(),
            application_base = AppDomain.CurrentDomain.BaseDirectory,
            current_directory = Environment.CurrentDirectory },
            sdk = new { path = Sdk, interface_assembly = typeof(IGrannyCurve).Assembly.FullName,
                animation_runtime_type = animation.GetType().FullName,
                animation_runtime_assembly = animation.GetType().Assembly.FullName,
                animation_runtime_path = animation.GetType().Assembly.Location,
                curve_runtime_type = tracks[0].PositionCurve.GetType().FullName,
                curve_runtime_assembly = tracks[0].PositionCurve.GetType().Assembly.FullName,
                curve_runtime_path = tracks[0].PositionCurve.GetType().Assembly.Location,
                loaded_granny_assemblies = LoadedAssemblies, assembly_resolve = AssemblyResolveLog },
            input = new { model = model.Name, animation = animation.Name, duration = animation.Duration,
                time_step = animation.TimeStep, oversampling = animation.Oversampling,
                track_group = groups[0].Name, tracks = tracks.Count, sampled_curves = tracks.Count * channels.Length },
            t0_comparison = new { compared_components = comparedComponents, max_absolute_error = maxT0Error,
                matches_existing_x86_track_curve_export = maxT0Error < 1e-5 },
            samples = sampleSummaries, most_changed_curve = dynamicSummary,
            forbidden_calls = new[] { "IGrannyAnimation.SampleBone was not called" } };
        var serializer = new JavaScriptSerializer();
        serializer.MaxJsonLength = 1024 * 1024;
        File.WriteAllText(outputPath, serializer.Serialize(info), new UTF8Encoding(false));
        GC.KeepAlive(modelFile); GC.KeepAlive(animationFile); GC.KeepAlive(context);
        return 0;
    }

    [MethodImpl(MethodImplOptions.NoInlining)]
    private static int SafeRun(string[] args)
    {
        return Run(args);
    }

    internal static int ConfigureAndRun(string[] args)
    {
        Require(args.Length == 4, "usage: GrannyAnimationProbe <sdk-dir> <gsd> <model.gr2> <idle.gr2>");
        Sdk = Path.GetFullPath(args[0]);
        for (int i = 1; i < args.Length; ++i) args[i] = Path.GetFullPath(args[i]);
        AppDomain.CurrentDomain.AssemblyLoad += delegate(object sender, AssemblyLoadEventArgs e)
        {
            string location = "";
            try { location = e.LoadedAssembly.Location; } catch { }
            LoadedAssemblies.Add(new { name = e.LoadedAssembly.FullName, path = location });
        };
        AppDomain.CurrentDomain.AssemblyResolve += delegate(object sender, ResolveEventArgs e)
        {
            string name = new AssemblyName(e.Name).Name;
            string path = Path.Combine(Sdk, name + ".dll");
            AssemblyResolveLog.Add(name + " => " + (File.Exists(path) ? path : "NOT_FOUND"));
            return File.Exists(path) ? Assembly.LoadFrom(path) : null;
        };
        Require(SetDllDirectory(Sdk), "Cannot set process-local SDK DLL search path");
        Directory.SetCurrentDirectory(Sdk);
        return SafeRun(args);
    }

    private static int Main(string[] args)
    {
        SetErrorMode(0x8003);
        try { WerSetFlags(0x10); } catch { }
        AppDomain domain = null;
        try
        {
            Require(args.Length == 4, "usage: GrannyAnimationProbe <sdk-dir> <gsd> <model.gr2> <idle.gr2>");
            string sdk = Path.GetFullPath(args[0]);
            for (int i = 1; i < args.Length; ++i) args[i] = Path.GetFullPath(args[i]);
            var setup = new AppDomainSetup
            {
                ApplicationBase = sdk,
                ConfigurationFile = Assembly.GetExecutingAssembly().Location + ".config"
            };
            domain = AppDomain.CreateDomain("GrannyAnimationProbeX64", null, setup);
            string executable = Assembly.GetExecutingAssembly().Location;
            var runner = (GrannyProbeRunner)domain.CreateInstanceFromAndUnwrap(
                executable, typeof(GrannyProbeRunner).FullName);
            return runner.Execute(args);
        }
        catch (Exception error)
        {
            Console.Error.WriteLine(error.GetType().FullName + ": " + error.Message);
            Console.Error.WriteLine(error.StackTrace);
            return 1;
        }
        finally
        {
            if (domain != null)
            {
                try { AppDomain.Unload(domain); } catch { }
            }
        }
    }
}

public sealed class GrannyProbeRunner : MarshalByRefObject
{
    public int Execute(string[] args)
    {
        return GrannyAnimationProbe.ConfigureAndRun(args);
    }
}
