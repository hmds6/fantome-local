using System;
using System.Diagnostics;
using System.IO;
using System.Windows.Forms;
using System.Threading;
static class Launcher {
    [STAThread] static void Main(string[] args) {
        bool created;
        using (var gate = new Mutex(true, "Local\\FantomeLocal-Soufi", out created)) {
        if (!created) { MessageBox.Show("Fantome Local est déjà ouvert.", "Fantome Local"); return; }
        try {
            string root = AppDomain.CurrentDomain.BaseDirectory;
            string pythons = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), @"Programs\Python");
            string python = null;
            foreach (string v in new[] { "Python314", "Python313" }) {
                string p = Path.Combine(pythons, v + @"\pythonw.exe");
                if (File.Exists(p)) { python = p; break; }
            }
            if (python == null) throw new Exception("Python 3.13 ou 3.14 local introuvable dans " + pythons + ".");
            var start = new ProcessStartInfo(python, "\"" + Path.Combine(root, "app.py") + "\"" + (Array.IndexOf(args, "--start") >= 0 ? " --start" : ""));
            start.WorkingDirectory = root;
            start.UseShellExecute = false;
            start.CreateNoWindow = true;
            using (var child = Process.Start(start)) {
                child.WaitForExit();
                if (child.ExitCode != 0) MessageBox.Show("L’interface s’est arrêtée avec le code " + child.ExitCode + ". Lancez app.py avec Python pour obtenir le détail.", "Fantome Local");
            }
        } catch (Exception e) { MessageBox.Show(e.Message, "Fantome Local"); }
        }
    }
}
