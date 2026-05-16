# linkedin/admin.py
from django.contrib import admin

from crm.models import Deal, Lead, LeadDiscovery
from linkedin.admin_export import export_xlsx_action
from linkedin.models import ActionLog, Campaign, LinkedInProfile, SearchKeyword, SiteConfig, Task


@admin.register(SiteConfig)
class SiteConfigAdmin(admin.ModelAdmin):
    list_display = ("__str__", "llm_provider", "ai_model", "llm_api_base")

    def has_add_permission(self, request):
        return not SiteConfig.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Campaign)
class CampaignAdmin(admin.ModelAdmin):
    list_display = ("name", "booking_link")
    filter_horizontal = ("users",)
    fieldsets = (
        (None, {"fields": ("name", "users", "booking_link")}),
        ("ICP & qualification", {"fields": ("product_docs", "campaign_objective")}),
        ("Discovery keywords", {
            "fields": ("seed_public_ids", "job_keywords", "content_keywords", "persona_keywords"),
            "description": (
                "job_keywords: hiring-role keywords (e.g. 'Customer Success Operations'). "
                "content_keywords: post-topic keywords (e.g. 'customer churn'). "
                "persona_keywords: buyer titles used to find contacts at companies "
                "discovered via job signals (e.g. 'VP Customer Success'). "
                "All three are JSON lists of strings."
            ),
        }),
    )


@admin.register(Lead)
class LeadAdmin(admin.ModelAdmin):
    list_display = ("public_identifier", "linkedin_url", "disqualified", "creation_date")
    list_filter = ("disqualified",)
    search_fields = ("public_identifier", "linkedin_url", "urn")
    readonly_fields = ("creation_date", "update_date")
    actions = [export_xlsx_action(
        filename="leads",
        columns=[
            ("Public Identifier", "public_identifier"),
            ("LinkedIn URL", "linkedin_url"),
            ("URN", "urn"),
            ("Disqualified", "disqualified"),
            ("Created", "creation_date"),
            ("Updated", "update_date"),
        ],
    )]


@admin.register(LeadDiscovery)
class LeadDiscoveryAdmin(admin.ModelAdmin):
    list_display = ("lead", "source", "keyword", "discovered_at")
    list_filter = ("source",)
    raw_id_fields = ("lead",)
    date_hierarchy = "discovered_at"
    actions = [export_xlsx_action(
        filename="lead_discoveries",
        columns=[
            ("Lead", "lead.public_identifier"),
            ("LinkedIn URL", "lead.linkedin_url"),
            ("Source", "source"),
            ("Keyword", "keyword"),
            ("Discovered At", "discovered_at"),
        ],
    )]


@admin.register(Deal)
class DealAdmin(admin.ModelAdmin):
    list_display = ("lead", "campaign", "state", "source", "outcome", "creation_date")
    list_filter = ("source", "state", "outcome", "campaign")
    search_fields = ("lead__public_identifier", "lead__linkedin_url", "reason")
    raw_id_fields = ("lead", "campaign")
    readonly_fields = ("creation_date", "update_date")
    date_hierarchy = "creation_date"
    actions = [export_xlsx_action(
        filename="deals",
        columns=[
            ("Lead", "lead.public_identifier"),
            ("LinkedIn URL", "lead.linkedin_url"),
            ("Campaign", "campaign.name"),
            ("State", "state"),
            ("Source", "source"),
            ("Outcome", "outcome"),
            ("Reason", "reason"),
            ("Created", "creation_date"),
            ("Updated", "update_date"),
        ],
    )]


@admin.register(LinkedInProfile)
class LinkedInProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "linkedin_username", "active", "legal_accepted")
    list_filter = ("active",)
    raw_id_fields = ("user", "self_lead")


@admin.register(SearchKeyword)
class SearchKeywordAdmin(admin.ModelAdmin):
    list_display = ("keyword", "campaign", "used", "used_at")
    list_filter = ("used", "campaign")
    raw_id_fields = ("campaign",)


@admin.register(ActionLog)
class ActionLogAdmin(admin.ModelAdmin):
    list_display = ("action_type", "linkedin_profile", "campaign", "created_at")
    list_filter = ("action_type", "campaign")
    raw_id_fields = ("linkedin_profile", "campaign")
    date_hierarchy = "created_at"
    readonly_fields = ("linkedin_profile", "campaign", "action_type", "created_at")


@admin.register(Task)
class TaskAdmin(admin.ModelAdmin):
    list_display = ("task_type", "status", "scheduled_at", "payload", "created_at")
    list_filter = ("task_type", "status")
    readonly_fields = (
        "task_type", "status", "scheduled_at", "payload",
        "created_at", "started_at", "completed_at",
    )
    date_hierarchy = "scheduled_at"


