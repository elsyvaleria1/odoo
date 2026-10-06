{
    "name": "Speech Tests",
    "version": "19.0.1.0.0",
    "category": "Hidden/Tests",
    "sequence": 9876,
    "summary": "Test Speech behaviour, including media segment, speech pipeline, subtitle routes",
    "description": "Run regression tests for Speech. Loaded test suites include ``TestMediaSegment``, ``TestSegmentOwnership``, ``TestTheMixinDoesNotSquatAConsumersFieldNames``, ``TestTranscription``, ``TestTimeline``.",
    "author": "AgroMarin",
    "website": "https://www.agromarin.mx",
    "license": "LGPL-3",
    "depends": [
        "speech",
        "mail_speech",
        "speech_ai",
        "speech_analysis",
    ],
    "data": [
        "security/ir.access.csv",
    ],
}
