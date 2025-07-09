namespace TypeTreeGeneratorAPI.TypeTreeGenerator
{
    public class TypeTreeGeneratorHandle
    {
        public TypeTreeGenerator Instance { get; }

        public TypeTreeGeneratorHandle(string type, string unityVersionString)
        {
            switch (type)
            {
                case "AssetsTools":
                    Instance = new AssetsTools.AssetsToolsGenerator(unityVersionString);
                    break;
                default:
                    throw new ArgumentException($"Unknown TypeTreeGenerator type: {type}");
            }
        }
    }
}
