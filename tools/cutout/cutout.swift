// cutout — lift the subject off its background with Apple Vision (macOS 14+), on this Mac.
//   cutout <in.jpg> <out.png> [instance,instance…|all|count]
// Writes a transparent PNG cropped to the subject, and prints JSON: instances found, the
// ones kept, and the subject's bounding box as fractions of the frame.
import Foundation
import Vision
import CoreImage
import CoreImage.CIFilterBuiltins
import UniformTypeIdentifiers

let args = CommandLine.arguments
guard args.count >= 3 else { print("usage: cutout in out.png [ids|all]"); exit(2) }
let url = URL(fileURLWithPath: args[1])
guard let src = CIImage(contentsOf: url, options: [.applyOrientationProperty: true]) else { print("{\"error\":\"read\"}"); exit(1) }
let handler = VNImageRequestHandler(ciImage: src)
let req = VNGenerateForegroundInstanceMaskRequest()
do { try handler.perform([req]) } catch { print("{\"error\":\"vision\"}"); exit(1) }
guard let obs = req.results?.first else { print("{\"instances\":0}"); exit(0) }
if args.count >= 4 && args[3] == "count" { print("{\"instances\":\(obs.allInstances.count)}"); exit(0) }
var keep = obs.allInstances
if args.count >= 4 && args[3] != "all" {
    keep = IndexSet(args[3].split(separator: ",").compactMap { Int($0) })
}
let maskBuf = try obs.generateScaledMaskForImage(forInstances: keep, from: handler)
let mask = CIImage(cvPixelBuffer: maskBuf)
let f = CIFilter.blendWithMask()
f.inputImage = src
f.backgroundImage = CIImage.empty()
f.maskImage = mask
guard var out = f.outputImage else { exit(1) }
// crop to the mask's extent of non-zero alpha, with a small margin
let ctx = CIContext()
let ext = src.extent
var box = ext
if let cg = ctx.createCGImage(mask, from: mask.extent) {
    let w = cg.width, h = cg.height
    var data = [UInt8](repeating: 0, count: w * h)
    let cs = CGColorSpaceCreateDeviceGray()
    if let bc = CGContext(data: &data, width: w, height: h, bitsPerComponent: 8, bytesPerRow: w, space: cs, bitmapInfo: 0) {
        bc.draw(cg, in: CGRect(x: 0, y: 0, width: w, height: h))
        var minX = w, minY = h, maxX = -1, maxY = -1
        for y in 0..<h { for x in 0..<w where data[y * w + x] > 40 {
            if x < minX { minX = x }; if x > maxX { maxX = x }; if y < minY { minY = y }; if y > maxY { maxY = y } } }
        if maxX >= 0 {
            let m = Int(Double(max(maxX - minX, maxY - minY)) * 0.04)
            minX = max(0, minX - m); minY = max(0, minY - m); maxX = min(w - 1, maxX + m); maxY = min(h - 1, maxY + m)
            // bitmap rows run top-down; CI coordinates run bottom-up
            box = CGRect(x: CGFloat(minX), y: CGFloat(h - 1 - maxY), width: CGFloat(maxX - minX + 1), height: CGFloat(maxY - minY + 1))
        }
    }
}
out = out.cropped(to: box)
let cs = CGColorSpace(name: CGColorSpace.sRGB)!
try ctx.writePNGRepresentation(of: out, to: URL(fileURLWithPath: args[2]), format: .RGBA8, colorSpace: cs)
let fx = box.minX / ext.width, fy = 1 - box.maxY / ext.height
print("{\"instances\":\(obs.allInstances.count),\"kept\":\(Array(keep)),\"box\":[\(String(format: "%.4f", fx)),\(String(format: "%.4f", fy)),\(String(format: "%.4f", box.width / ext.width)),\(String(format: "%.4f", box.height / ext.height))]}")
