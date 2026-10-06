{
    "name": "Approval Tests",
    "version": "19.0.1.3.0",
    "category": "Hidden/Tests",
    "summary": "Test Approval behaviour, including admission not in context, approval access, approval mixin",
    "description": "Run regression tests for Approval. Loaded test suites include ``TestAdmissionNotInContext``, ``TestApprovalAccess``, ``TestApprovalMixin``, ``TestApprovalSubjects``, ``TestBindingOnAnAdopter``.",
    "author": "AgroMarin",
    "license": "LGPL-3",
    "depends": [
        "approval",
        "approval_automation",
    ],
    "data": [
        "security/ir_access.xml",
        "data/approval_binding_data.xml",
    ],
}
