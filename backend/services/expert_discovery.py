from services.expert_manager import expert_manager


DISCOVERY = {

    "Software Architect": [

        {
            "title": "Project",
            "fields": [
                {
                    "name": "project_name",
                    "label": "Project Name",
                    "placeholder": "Example: ExpertOS"
                },
                {
                    "name": "description",
                    "label": "Tell Ethan About Your Project",
                    "placeholder": "Describe your project, goals and current challenges..."
                }
            ]
        },

        {
            "title": "Context",
            "fields": [
                {
                    "name": "tech_stack",
                    "label": "Current Tech Stack",
                    "placeholder": "React, Flask, Node..."
                },
                {
                    "name": "context",
                    "label": "Current Challenges",
                    "placeholder": "Scalability, APIs, architecture..."
                }
            ]
        },

        {
            "title": "Goals",
            "fields": [
                {
                    "name": "goals",
                    "label": "Project Goals",
                    "placeholder": "Business goals..."
                },
                {
                    "name": "constraints",
                    "label": "Constraints",
                    "placeholder": "Budget, deadline, team size..."
                }
            ]
        }

    ],

    "Database Engineer": [

        {
            "title": "Project",
            "fields": [
                {
                    "name": "project_name",
                    "label": "Project Name",
                    "placeholder": "Example: ExpertOS"
                },
                {
                    "name": "description",
                    "label": "Describe Your Data",
                    "placeholder": "What kind of application are you building?"
                }
            ]
        },

        {
            "title": "Context",
            "fields": [
                {
                    "name": "database",
                    "label": "Current Database",
                    "placeholder": "MySQL, PostgreSQL..."
                },
                {
                    "name": "volume",
                    "label": "Expected Data Size",
                    "placeholder": "Thousands, millions..."
                }
            ]
        },

        {
            "title": "Goals",
            "fields": [
                {
                    "name": "performance",
                    "label": "Performance Goals",
                    "placeholder": "Fast reads, analytics..."
                },
                {
                    "name": "constraints",
                    "label": "Constraints",
                    "placeholder": "Budget, hosting..."
                }
            ]
        }

    ],

    "Security Expert": [

        {
            "title": "Project",
            "fields": [
                {
                    "name": "project_name",
                    "label": "Project Name",
                    "placeholder": "Example: ExpertOS"
                },
                {
                    "name": "description",
                    "label": "Describe Your Application",
                    "placeholder": "What does your software do?"
                }
            ]
        },

        {
            "title": "Context",
            "fields": [
                {
                    "name": "authentication",
                    "label": "Authentication",
                    "placeholder": "JWT, OAuth..."
                },
                {
                    "name": "security",
                    "label": "Current Security Concerns",
                    "placeholder": "Data leaks, attacks..."
                }
            ]
        },

        {
            "title": "Goals",
            "fields": [
                {
                    "name": "compliance",
                    "label": "Compliance",
                    "placeholder": "GDPR, HIPAA..."
                },
                {
                    "name": "constraints",
                    "label": "Constraints",
                    "placeholder": "Budget, deadlines..."
                }
            ]
        }

    ],

    "Cloud Consultant": [

        {
            "title": "Project",
            "fields": [
                {
                    "name": "project_name",
                    "label": "Project Name",
                    "placeholder": "Example: ExpertOS"
                },
                {
                    "name": "description",
                    "label": "Describe Your Infrastructure",
                    "placeholder": "Current hosting..."
                }
            ]
        },

        {
            "title": "Context",
            "fields": [
                {
                    "name": "cloud",
                    "label": "Current Cloud",
                    "placeholder": "AWS, Azure..."
                },
                {
                    "name": "traffic",
                    "label": "Expected Traffic",
                    "placeholder": "Users per month..."
                }
            ]
        },

        {
            "title": "Goals",
            "fields": [
                {
                    "name": "goals",
                    "label": "Infrastructure Goals",
                    "placeholder": "High availability..."
                },
                {
                    "name": "constraints",
                    "label": "Budget",
                    "placeholder": "Cloud budget..."
                }
            ]
        }

    ],

    "DevOps Engineer": [

        {
            "title": "Project",
            "fields": [
                {
                    "name": "project_name",
                    "label": "Project Name",
                    "placeholder": "Example: ExpertOS"
                },
                {
                    "name": "description",
                    "label": "Describe Your Deployment",
                    "placeholder": "Current deployment..."
                }
            ]
        },

        {
            "title": "Context",
            "fields": [
                {
                    "name": "pipeline",
                    "label": "CI/CD",
                    "placeholder": "GitHub Actions..."
                },
                {
                    "name": "deployment",
                    "label": "Deployment Problems",
                    "placeholder": "Manual deployment..."
                }
            ]
        },

        {
            "title": "Goals",
            "fields": [
                {
                    "name": "goals",
                    "label": "Automation Goals",
                    "placeholder": "One-click deployment..."
                },
                {
                    "name": "constraints",
                    "label": "Constraints",
                    "placeholder": "Infrastructure..."
                }
            ]
        }

    ],

    "Design Advisor": [

        {
            "title": "Project",
            "fields": [
                {
                    "name": "project_name",
                    "label": "Project Name",
                    "placeholder": "Example: ExpertOS"
                },
                {
                    "name": "description",
                    "label": "Describe Your Product",
                    "placeholder": "Who will use it?"
                }
            ]
        },

        {
            "title": "Context",
            "fields": [
                {
                    "name": "users",
                    "label": "Target Users",
                    "placeholder": "Developers..."
                },
                {
                    "name": "problems",
                    "label": "UX Problems",
                    "placeholder": "Navigation..."
                }
            ]
        },

        {
            "title": "Goals",
            "fields": [
                {
                    "name": "goals",
                    "label": "Experience Goals",
                    "placeholder": "Simple, modern..."
                },
                {
                    "name": "constraints",
                    "label": "Constraints",
                    "placeholder": "Brand guidelines..."
                }
            ]
        }

    ]

}


def get_discovery(expert):

    return DISCOVERY.get(expert, [])