// Prints the Mac's cameras as "<OpenCV index>\t<name>", in the same order OpenCV numbers them
// (OpenCV's AVFoundation backend: video + muxed devices, sorted by uniqueID). Used by camera.py.
import AVFoundation

let devices = (AVCaptureDevice.devices(for: .video) + AVCaptureDevice.devices(for: .muxed))
    .sorted { $0.uniqueID < $1.uniqueID }
for (i, d) in devices.enumerated() {
    print("\(i)\t\(d.localizedName)")
}
