// Original-input-preserving preparation using the installed x86 Civ V SDK; runtime is x64.
// Stock GR2 names live in the separate original GSD, which must be loaded first.
using System;
using System.Collections.Generic;
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
using NexusBuddy.GrannyWrappers;

internal static class StockUnitExporter
{
    private static string Sdk;
    [DllImport("kernel32.dll", CharSet = CharSet.Unicode)] private static extern bool SetDllDirectory(string path);
    [DllImport("kernel32.dll")] private static extern uint SetErrorMode(uint mode);

    private static void Require(bool value, string message)
    {
        if (!value) throw new InvalidDataException(message);
    }

    private static string Hash(string path)
    {
        using (SHA256 hash = SHA256.Create())
        using (FileStream stream = File.OpenRead(path))
            return BitConverter.ToString(hash.ComputeHash(stream)).Replace("-", "").ToLowerInvariant();
    }

    private static void Floats(float[] values, int count, string label)
    {
        Require(values != null && values.Length == count, label + " count");
        Require(values.All(x => !float.IsNaN(x) && !float.IsInfinity(x)), label + " finite values");
    }

    private static float[] Identity()
    {
        return new float[] {1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1};
    }

    private static float[] Multiply(float[] a, float[] b)
    {
        float[] result = new float[16];
        for (int row = 0; row < 4; ++row)
            for (int col = 0; col < 4; ++col)
            {
                double value = 0;
                for (int k = 0; k < 4; ++k) value += (double)a[row + 4 * k] * b[k + 4 * col];
                result[row + 4 * col] = (float)value;
            }
        Floats(result, 16, "Composed matrix");
        return result;
    }

    private static float[] LocalMatrix(float[] position, float[] quaternion, float[] scale, bool transposeScale)
    {
        Floats(position, 3, "Local position");
        Floats(quaternion, 4, "Local quaternion");
        Floats(scale, 9, "Local scale shear");
        double norm = Math.Sqrt(quaternion.Sum(v => (double)v * v));
        Require(norm > 0.99 && norm < 1.01, "Local quaternion is not near unit length");
        double x = quaternion[0] / norm, y = quaternion[1] / norm, z = quaternion[2] / norm, w = quaternion[3] / norm;
        // Column-vector quaternion rotation. Bind matrices below independently check
        // this convention against every original inverse-world skeleton matrix.
        float[] rotation = new float[] {
            (float)(1-2*y*y-2*z*z), (float)(2*x*y+2*w*z), (float)(2*x*z-2*w*y), 0,
            (float)(2*x*y-2*w*z), (float)(1-2*x*x-2*z*z), (float)(2*y*z+2*w*x), 0,
            (float)(2*x*z+2*w*y), (float)(2*y*z-2*w*x), (float)(1-2*x*x-2*y*y), 0,
            0, 0, 0, 1};
        float[] shear = Identity();
        for (int row = 0; row < 3; ++row)
            for (int col = 0; col < 3; ++col)
                shear[row + 4 * col] = scale[transposeScale ? col + 3 * row : row + 3 * col];
        float[] result = Multiply(rotation, shear);
        result[12] = position[0]; result[13] = position[1]; result[14] = position[2];
        return result;
    }

    private static float[][] ComposeWorld(float[][] local, int[] parents)
    {
        float[][] world = new float[local.Length][];
        bool[] visiting = new bool[local.Length];
        Func<int, float[]> visit = null;
        visit = delegate(int i)
        {
            Require(!visiting[i], "Skeleton parent cycle");
            if (world[i] != null) return world[i];
            visiting[i] = true;
            world[i] = parents[i] < 0 ? local[i] : Multiply(visit(parents[i]), local[i]);
            visiting[i] = false;
            return world[i];
        };
        for (int i = 0; i < local.Length; ++i) visit(i);
        return world;
    }

    private static float[] SampleCurve(IGrannyCurve curve, float[] identity, float duration, bool normalize)
    {
        Require(curve != null, "Missing original animation curve");
        if (curve.IsIdentity) return identity;
        Require(curve.Dimension == identity.Length && curve.KnotCount > 0 && curve.KnotCount <= 100000,
                "Animation curve dimensions/count outside bound");
        float[] value = curve.Sample(0f, duration, normalize, false, false);
        Floats(value, identity.Length, "Sampled original curve");
        return value;
    }

    private static int Main(string[] args)
    {
        SetErrorMode(0x8003);
        try
        {
            Require(args.Length == 5, "usage: StockUnitExporter <sdk-dir> <names.gsd> <model.gr2> <idle.gr2> <output.json>");
            for (int i = 0; i < args.Length; ++i) args[i] = Path.GetFullPath(args[i]);
            Sdk = args[0];
            AppDomain.CurrentDomain.AssemblyResolve += delegate(object sender, ResolveEventArgs e)
            {
                string name = new AssemblyName(e.Name).Name;
                string own = Path.Combine(AppDomain.CurrentDomain.BaseDirectory, name + ".dll");
                if (File.Exists(own)) return Assembly.LoadFrom(own);
                string path = Path.Combine(Sdk, name + ".dll");
                return File.Exists(path) ? Assembly.LoadFrom(path) : null;
            };
            SetDllDirectory(Sdk);
            Directory.SetCurrentDirectory(Sdk);
            return Export(args);
        }
        catch (Exception error)
        {
            Console.Error.WriteLine(error.ToString());
            return 1;
        }
    }

    // Keep SDK references out of Main's JIT dependency loading until the resolver is set.
    [MethodImpl(MethodImplOptions.NoInlining)]
    private static int Export(string[] args)
    {
        for (int i = 1; i <= 3; ++i)
            Require(File.Exists(args[i]) && new FileInfo(args[i]).Length > 0 &&
                    new FileInfo(args[i]).Length <= 64 * 1024 * 1024, "Missing or oversized input");
        Require(!File.Exists(args[4]), "Refusing to replace an export");
        string gsdHash = Hash(args[1]), modelHash = Hash(args[2]), animationHash = Hash(args[3]);
        VirtualSpace virtualSpace = new VirtualSpace();
        virtualSpace.BasePaths = new List<string>();
        Context.Add(virtualSpace);
        Context.Add(new ProjectConfig());
        GrannyContext context = new GrannyContext();
        Context.Add(context);
        Console.WriteLine("LOAD_STRING_DATABASE=" + args[1]);
        context.LoadStringDatabase(args[1]);
        Console.WriteLine("LOAD_MODEL=" + args[2]);
        IGrannyFile modelFile = context.LoadGrannyFile(args[2]);
        Require(modelFile != null && modelFile.Models.Count == 1 && modelFile.Meshes.Count == 1,
                "Expected one stock model and mesh");
        IGrannyModel model = modelFile.Models[0];
        Require(!String.IsNullOrWhiteSpace(model.Name), "Missing model name after GSD load");
        Require(model.Skeleton != null && model.Skeleton.Bones.Count > 0 && model.Skeleton.Bones.Count <= 256,
                "Invalid model skeleton");
        var bones = model.Skeleton.Bones;
        Require(bones.All(b => !String.IsNullOrWhiteSpace(b.Name)) &&
                bones.Select(b => b.Name).Distinct().Count() == bones.Count, "Missing or duplicate bone names");
        foreach (var bone in bones)
        {
            Require(bone.ParentIndex >= -1 && bone.ParentIndex < bones.Count, "Bone parent out of bounds");
            Floats(bone.InverseWorldTransform, 16, "Inverse bind matrix");
        }
        var meshes = modelFile.Meshes.Select(mesh =>
        {
            Require(!String.IsNullOrWhiteSpace(mesh.Name) && mesh.VertexCount > 0 && mesh.VertexCount <= 200000 &&
                    mesh.IndexCount > 0 && mesh.IndexCount <= 600000 && mesh.IndexCount % 3 == 0,
                    "Invalid mesh name or count");
            Console.WriteLine("MESH=" + mesh.Name + " VERTICES=" + mesh.VertexCount + " INDICES=" + mesh.IndexCount);
            GrannyMeshWrapper wrapper = new GrannyMeshWrapper(mesh);
            var info = wrapper.getMeshInfo();
            Require(info.vertices.Count == mesh.VertexCount && info.triangles.Count * 3 == mesh.IndexCount,
                    "SDK/wrapper mesh count mismatch");
            Require(info.boneBindings.Count > 0 && info.boneBindings.Count <= 32 &&
                    info.boneBindings.Distinct().Count() == info.boneBindings.Count &&
                    info.boneBindings.All(n => bones.Any(b => b.Name == n)), "Invalid mesh bone bindings");
            Require(info.vertexStructInfos.All(a => !String.IsNullOrWhiteSpace(a.name)), "Unresolved vertex descriptor name");
            foreach (var vertex in info.vertices)
            {
                Floats(vertex.position, 3, "Position");
                Floats(vertex.normal, 3, "Normal");
                Floats(vertex.uv, 2, "UV");
                Require(vertex.boneIndices != null && vertex.boneIndices.Length == 4 &&
                        vertex.boneWeights != null && vertex.boneWeights.Length == 4 &&
                        vertex.boneWeights.All(w => w >= 0 && w <= 255) && vertex.boneWeights.Sum() == 255,
                        "Invalid skin weight sum");
                Require(Enumerable.Range(0, 4).All(i => vertex.boneWeights[i] == 0 ||
                        (vertex.boneIndices[i] >= 0 && vertex.boneIndices[i] < info.boneBindings.Count)),
                        "Skin binding index outside mesh");
            }
            Require(info.triangles.All(t => t.Length == 3 && t.All(i => i >= 0 && i < mesh.VertexCount)),
                    "Triangle index outside mesh");
            Require(mesh.MaterialBindings.Count == 1, "Expected one original stock material");
            var materials = mesh.MaterialBindings.Select(material =>
            {
                Require(material.ShaderSet == "UnitShader_Skinned", "Unsupported original shader: " + material.ShaderSet);
                var textures = material.FindParameterSet("UnitShaderTextures");
                Require(textures != null, "Missing original unit texture parameters");
                string diffuse = Convert.ToString(textures.GetParameterValue("BaseTextureMap"));
                string sref = Convert.ToString(textures.GetParameterValue("SREFMap"));
                Require(!String.IsNullOrWhiteSpace(diffuse) && !String.IsNullOrWhiteSpace(sref), "Missing original texture reference");
                Console.WriteLine("MATERIAL=" + material.Name + " ALPHA=" + material.AlphaMode + " DIFFUSE=" + diffuse);
                return new {name = material.Name, shader = material.ShaderSet,
                            alpha = Convert.ToString(material.AlphaMode), skinBones = material.SkinBoneCount,
                            diffuse = diffuse, sref = sref};
            }).ToArray();
            return new {name = mesh.Name, bindings = info.boneBindings, materials = materials,
                        attributes = info.vertexStructInfos.Select(a => new {name = a.name, type = a.type,
                                      count = a.count, offset = a.offset, element_bytes = a.length}).ToArray(),
                        stride = info.bytesPerVertex,
                        vertices = info.vertices.Select(v => new {position = v.position, normal = v.normal,
                                   uv = v.uv, boneIndices = v.boneIndices, boneWeights = v.boneWeights}).ToArray(),
                        triangles = info.triangles};
        }).ToArray();
        Console.WriteLine("LOAD_IDLE=" + args[3]);
        IGrannyFile animationFile = context.LoadGrannyFile(args[3]);
        Require(animationFile != null && animationFile.Animations.Count == 1, "Expected one original idle animation");
        IGrannyAnimation animation = animationFile.Animations[0];
        Require(animation.Duration > 0 && !float.IsInfinity(animation.Duration) && !float.IsNaN(animation.Duration),
                "Invalid idle duration");
        Console.WriteLine("MODEL_NAME=" + model.Name + " ANIMATION=" + animation.Name + " TRACK_GROUPS=" +
                          String.Join(",", animation.TrackGroups.Select(t => t.Name).ToArray()));
        // The installed SDK's SampleBone/SampleAnimation path faults for this stock
        // model, including after a private resave. Evaluate its original curves
        // instead; never silently substitute a bind pose for the idle animation.
        int[] parents = bones.Select(b => b.ParentIndex).ToArray();
        // This SDK's LocalTransform.ScaleShear getter starts at the quaternion:
        // its first four returned values equal Orientation. Nexus Buddy's public
        // wrapper reads the actual 3x3 at bone+40. Check its other fields against
        // SDK values, then verify the entire bind hierarchy before using it.
        var bindScales = bones.Select(b =>
        {
            var wrapper = new GrannyBoneWrapper(b);
            Require(wrapper.getPosition().SequenceEqual(b.LocalTransform.Position) &&
                    wrapper.getOrientation().SequenceEqual(b.LocalTransform.Orientation) &&
                    wrapper.getInverseWorldMatrix().SequenceEqual(b.InverseWorldTransform),
                    "Bone wrapper/SDK layout disagreement");
            return wrapper.getScaleShear();
        }).ToArray();
        double[] bindErrors = new double[2];
        for (int layout = 0; layout < 2; ++layout)
        {
            var bindLocal = bones.Select((b, i) => LocalMatrix(b.LocalTransform.Position,
                b.LocalTransform.Orientation, bindScales[i], layout == 1)).ToArray();
            var bindWorld = ComposeWorld(bindLocal, parents);
            for (int i = 0; i < bones.Count; ++i)
            {
                float[] check = Multiply(bindWorld[i], bones[i].InverseWorldTransform);
                float[] identity = Identity();
                for (int j = 0; j < 16; ++j) bindErrors[layout] = Math.Max(bindErrors[layout], Math.Abs(check[j] - identity[j]));
            }
        }
        bool transposeScale = bindErrors[1] < bindErrors[0];
        double bindError = bindErrors[transposeScale ? 1 : 0];
        Console.WriteLine("BIND_MATRIX_MAX_ERROR=" + bindError + " TRANSPOSE_SCALE=" + transposeScale);
        if (bindError >= 0.002)
        {
            var diagnostic = new {source_sha256 = modelHash, gsd_sha256 = gsdHash, bind_errors = bindErrors,
                bones = bones.Select((b, i) => new {name = b.Name, parent = b.ParentIndex,
                    inverse = b.InverseWorldTransform, position = b.LocalTransform.Position,
                    orientation = b.LocalTransform.Orientation, scale = bindScales[i],
                    sdk_scale_getter = b.LocalTransform.ScaleShear}).ToArray()};
            File.WriteAllText(args[4] + ".skeleton.json", new JavaScriptSerializer().Serialize(diagnostic), new UTF8Encoding(false));
        }
        Require(bindError < 0.002, "Local skeleton composition does not match original inverse-world matrices");
        var groups = animation.TrackGroups.Where(g => g.Name == model.Name).ToArray();
        Require(groups.Length == 1, "Original animation has no unique matching model track group");
        var tracks = groups[0].TransformTracks;
        Require(tracks.Count > 0 && tracks.Count <= 512 && tracks.Select(t => t.Name).Distinct().Count() == tracks.Count,
                "Missing/duplicate transform track names");
        var localPose = new float[bones.Count][];
        var sampledTracks = new List<object>();
        for (int i = 0; i < bones.Count; ++i)
        {
            var matches = tracks.Where(t => t.Name == bones[i].Name).ToArray();
            Require(matches.Length <= 1, "Ambiguous bone animation track");
            if (matches.Length == 0)
            {
                var transform = bones[i].LocalTransform;
                localPose[i] = LocalMatrix(transform.Position, transform.Orientation, bindScales[i], transposeScale);
                continue;
            }
            var track = matches[0];
            Console.WriteLine("SAMPLE_TRACK_CURVES=" + track.Name);
            float[] position = SampleCurve(track.PositionCurve, new float[] {0, 0, 0}, animation.Duration, false);
            float[] rotation = SampleCurve(track.OrientationCurve, new float[] {0, 0, 0, 1}, animation.Duration, true);
            float[] scale = SampleCurve(track.ScaleShearCurve, new float[] {1, 0, 0, 0, 1, 0, 0, 0, 1}, animation.Duration, false);
            // If bind scales cannot disambiguate layout, sampled diagonal scales
            // are layout-independent. Fail on a new shear instead of guessing it.
            if (Math.Abs(bindErrors[0] - bindErrors[1]) < 1e-7)
                for (int row = 0; row < 3; ++row)
                    for (int col = 0; col < 3; ++col)
                        Require(Math.Abs(scale[row + 3 * col] - scale[col + 3 * row]) < 1e-6,
                                "Animation shear layout needs independent evidence");
            localPose[i] = LocalMatrix(position, rotation, scale, transposeScale);
            sampledTracks.Add(new {name = track.Name, position = position, orientation = rotation, scale_shear = scale,
                                   position_identity = track.PositionCurve.IsIdentity,
                                   orientation_identity = track.OrientationCurve.IsIdentity,
                                   scale_identity = track.ScaleShearCurve.IsIdentity});
        }
        var matrices = ComposeWorld(localPose, parents);
        var data = new {source_sha256 = modelHash, gsd_sha256 = gsdHash, animation_sha256 = animationHash,
                        models = new[] {new {name = model.Name, bones = bones.Select((b, i) => new {
                            name = b.Name, parent = b.ParentIndex, inverse = b.InverseWorldTransform,
                            local_position = b.LocalTransform.Position, local_orientation = b.LocalTransform.Orientation,
                            local_scale_shear = bindScales[i], sdk_scale_getter = b.LocalTransform.ScaleShear}).ToArray()}},
                        meshes = meshes,
                        pose = new {time = 0, duration = animation.Duration, animation = animation.Name,
                                    method = "original_track_curve_samples", bind_matrix_max_error = bindError,
                                    scale_shear_transposed = transposeScale, sampled_tracks = sampledTracks,
                                    bone_names = bones.Select(b => b.Name).ToArray(), matrices = matrices}};
        Require(Hash(args[1]) == gsdHash && Hash(args[2]) == modelHash && Hash(args[3]) == animationHash,
                "Preparation changed source inputs");
        JavaScriptSerializer serializer = new JavaScriptSerializer();
        serializer.MaxJsonLength = 32 * 1024 * 1024;
        File.WriteAllText(args[4], serializer.Serialize(data), new UTF8Encoding(false));
        GC.KeepAlive(modelFile);
        GC.KeepAlive(animationFile);
        GC.KeepAlive(context);
        Console.WriteLine("PASS_STOCK_UNIT_EXPORT=" + args[4]);
        return 0;
    }
}
