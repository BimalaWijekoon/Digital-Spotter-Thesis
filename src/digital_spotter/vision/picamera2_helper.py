"""System-Python Picamera2 owner for the measured split-runtime camera path."""

from __future__ import annotations

import argparse
import os
import socket
import struct


FRAME_MAGIC = b"DSCF"
FRAME_HEADER = struct.Struct("!4sQQQIIIIII")


def _connect(path: str) -> socket.socket:
    connection = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    connection.connect(path)
    return connection


def run(args: argparse.Namespace) -> int:
    from picamera2 import Picamera2

    camera = Picamera2()
    frame_duration_us = round(1_000_000 / args.fps)
    configuration = camera.create_video_configuration(
        main={"size": (args.main_width, args.main_height), "format": "YUV420"},
        lores={
            "size": (args.analysis_width, args.analysis_height),
            "format": "YUV420",
        },
        display=None,
        encode="main",
        queue=False,
        buffer_count=6,
        controls={"FrameDurationLimits": (frame_duration_us, frame_duration_us)},
    )
    camera.configure(configuration)
    recording = False
    if args.publish_url:
        from picamera2.encoders import H264Encoder
        from picamera2.outputs import PyavOutput

        camera.start_recording(
            H264Encoder(repeat=True, iperiod=args.fps),
            PyavOutput(
                args.publish_url,
                format="rtsp",
                options={"rtsp_transport": "tcp"},
            ),
            name="main",
        )
        recording = True
    elif args.encode_h264:
        from picamera2.encoders import H264Encoder
        from picamera2.outputs import FileOutput

        camera.start_recording(
            H264Encoder(repeat=True, iperiod=args.fps),
            FileOutput(os.devnull),
            name="main",
        )
        recording = True
    else:
        camera.start()

    connection = _connect(args.socket)
    sequence = 0
    last_sensor_timestamp_ns = None
    try:
        while True:
            request = camera.capture_request()
            try:
                metadata = request.get_metadata()
                sensor_timestamp_ns = metadata["SensorTimestamp"]
                exposure_time_us = metadata["ExposureTime"]
                array = request.make_array("lores")
                payload = array.tobytes(order="C")
                array_rows, array_columns = array.shape[:2]
            finally:
                request.release()
            sequence += 1
            dropped = 0
            if last_sensor_timestamp_ns is not None:
                interval_ns = round(1_000_000_000 / args.fps)
                elapsed_ns = sensor_timestamp_ns - last_sensor_timestamp_ns
                dropped = max(0, round(elapsed_ns / interval_ns) - 1)
            last_sensor_timestamp_ns = sensor_timestamp_ns
            header = FRAME_HEADER.pack(
                FRAME_MAGIC,
                sequence,
                sensor_timestamp_ns,
                exposure_time_us,
                args.analysis_width,
                args.analysis_height,
                array_rows,
                array_columns,
                len(payload),
                dropped,
            )
            connection.sendall(header)
            connection.sendall(payload)
            acknowledgement = connection.recv(1)
            if acknowledgement != b"C":
                break
    finally:
        connection.close()
        try:
            if recording:
                camera.stop_recording()
            else:
                camera.stop()
        finally:
            camera.close()
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--socket", required=True)
    parser.add_argument("--main-width", type=int, required=True)
    parser.add_argument("--main-height", type=int, required=True)
    parser.add_argument("--analysis-width", type=int, required=True)
    parser.add_argument("--analysis-height", type=int, required=True)
    parser.add_argument("--fps", type=int, required=True)
    parser.add_argument("--encode-h264", action="store_true")
    parser.add_argument("--publish-url")
    return run(parser.parse_args(argv))


if __name__ == "__main__":
    raise SystemExit(main())
