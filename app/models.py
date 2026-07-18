from pydantic import BaseModel, Field


class AcceptanceCriterion(BaseModel):
    given: str
    when: str
    then: str


class SuggestedUserStory(BaseModel):
    title: str
    summary: str


class Feature(BaseModel):
    title: str
    description: str
    problem_statement: str
    business_value: str
    functional_requirements: list[str] = Field(min_length=1)
    non_functional_requirements: list[str] = Field(default_factory=list)
    dependencies: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    priority: str = "MEDIUM"
    suggested_user_stories: list[SuggestedUserStory] = Field(default_factory=list)
    acceptance_criteria: list[AcceptanceCriterion] = Field(min_length=1)


class FeatureResponse(BaseModel):
    feature: Feature


class UserStory(BaseModel):
    title: str
    story: str = Field(description="As a ..., I want ..., so that ...")
    description: str
    priority: str = "MEDIUM"
    story_points: int = Field(ge=1,le=100)
    source_requirement_references: list[str] = Field(min_length=1)
    acceptance_criteria: list[AcceptanceCriterion] = Field(min_length=1)


class UserStoriesResponse(BaseModel):
    user_stories: list[UserStory]
