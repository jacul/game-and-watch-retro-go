// Optional local OCR for an attached crash photo; no desktop capture or UI access.
import Foundation
import Vision
import ImageIO
if CommandLine.arguments.count != 2 {
    fputs("Usage: swift crash_ocr.swift PHOTO\n", stderr)
    exit(2)
}
let url = URL(fileURLWithPath: CommandLine.arguments[1])
guard let source = CGImageSourceCreateWithURL(url as CFURL, nil),
      let image = CGImageSourceCreateImageAtIndex(source, 0, nil) else {
    fputs("Cannot read image\n", stderr)
    exit(1)
}
let request = VNRecognizeTextRequest()
request.recognitionLevel = .accurate
request.usesLanguageCorrection = false
do {
    try VNImageRequestHandler(cgImage: image, orientation: .right, options: [:]).perform([request])
    for result in request.results ?? [] {
        if let candidate = result.topCandidates(1).first { print(candidate.string) }
    }
} catch {
    fputs("OCR failed; inspect the supplied photo directly.\n", stderr)
    exit(1)
}
