import django_filters as df

from .models import Application, ApplicationStatus, ProjectProposal, ProposalStatus


class ApplicationFilter(df.FilterSet):
    status = df.ChoiceFilter(choices=ApplicationStatus.choices)

    class Meta:
        model = Application
        fields: list = []


class ProposalFilter(df.FilterSet):
    status = df.ChoiceFilter(choices=ProposalStatus.choices)

    class Meta:
        model = ProjectProposal
        fields: list = []
