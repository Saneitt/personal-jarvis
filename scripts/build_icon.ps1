$ErrorActionPreference='Stop'
$jarvisRoot=Split-Path $PSScriptRoot -Parent
Add-Type -AssemblyName System.Drawing
Add-Type -ReferencedAssemblies System.Drawing -TypeDefinition @'
using System;
using System.IO;
using System.Collections.Generic;
using System.Drawing;
using System.Drawing.Drawing2D;
using System.Drawing.Imaging;
public static class JarvisIconBuilder {
 public static void Build(string folder) {
  int[] sizes={16,24,32,48,64,128,256};
  var images=new List<byte[]>();
  foreach(int size in sizes)using(var bitmap=new Bitmap(size,size)) {
   using(var g=Graphics.FromImage(bitmap)) {
    g.SmoothingMode=SmoothingMode.AntiAlias;g.ScaleTransform(size/256f,size/256f);
    var shape=new GraphicsPath();shape.AddArc(0,0,120,120,180,90);shape.AddArc(136,0,120,120,270,90);shape.AddArc(136,136,120,120,0,90);shape.AddArc(0,136,120,120,90,90);shape.CloseFigure();
    using(var fill=new SolidBrush(Color.FromArgb(17,27,34)))g.FillPath(fill,shape);
    using(var ring=new Pen(Color.FromArgb(40,60,66),4))g.DrawEllipse(ring,37,37,182,182);
    using(var pen=new Pen(Color.FromArgb(227,212,158),10)) {
     pen.StartCap=pen.EndCap=LineCap.Round;
     g.DrawArc(pen,38,38,180,180,235,70);g.DrawArc(pen,38,38,180,180,-14,86);g.DrawArc(pen,38,38,180,180,108,86);
     var j=new GraphicsPath();j.AddLine(99,91,161,91);j.AddLine(161,91,161,148);j.AddBezier(161,148,161,189,99,189,99,148);g.DrawPath(pen,j);
    }
    using(var dot=new SolidBrush(Color.FromArgb(161,185,174)))g.FillEllipse(dot,123,30,10,10);
   }
   using(var stream=new MemoryStream()){bitmap.Save(stream,ImageFormat.Png);images.Add(stream.ToArray());}
   if(size==256)bitmap.Save(Path.Combine(folder,"jarvis.png"),ImageFormat.Png);
  }
  using(var writer=new BinaryWriter(File.Create(Path.Combine(folder,"jarvis.ico")))) {
   writer.Write((ushort)0);writer.Write((ushort)1);writer.Write((ushort)sizes.Length);
   int offset=6+16*sizes.Length;
   for(int i=0;i<sizes.Length;i++){writer.Write((byte)(sizes[i]==256?0:sizes[i]));writer.Write((byte)(sizes[i]==256?0:sizes[i]));writer.Write((byte)0);writer.Write((byte)0);writer.Write((ushort)1);writer.Write((ushort)32);writer.Write(images[i].Length);writer.Write(offset);offset+=images[i].Length;}
   foreach(var data in images)writer.Write(data);
  }
 }
}
'@
[JarvisIconBuilder]::Build((Join-Path $jarvisRoot 'web/assets'))
Write-Output 'Jarvis icon generated at 16-256 pixels.'
