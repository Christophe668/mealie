/* tslint:disable */

/**
/* This file was automatically generated from pydantic models by running pydantic2ts.
/* Do not modify it by hand - just update the pydantic models and then re-run the script
*/

export type FeedbackVerdict = "loved" | "ok" | "never_again";
export type PantryOutcome = "used_up" | "some_left";
export type PlanEntryType = "breakfast" | "lunch" | "dinner" | "side" | "snack" | "drink" | "dessert";
export type PantryLocation = "fridge" | "freezer" | "cupboard" | "other";
export type PantrySource = "shopping" | "manual" | "leftover";
export type GroupRecipeActionType = "link" | "post";
export type WebhookType = "mealplan";
export type Diet = "none" | "vegetarian" | "vegan" | "pescatarian" | "halal" | "kosher" | "other";

export interface CookedFeedback {
  verdict: FeedbackVerdict;
  effort?: number | null;
}
export interface CookedLeftovers {
  portions: number;
  location?: "fridge" | "freezer";
  useBy?: string | null;
}
export interface CookedMealCreate {
  recipeId: string;
  cookedOn: string;
  mealPlanEntryId?: number | null;
  scale?: number | null;
  pantry?: CookedPantryOutcome[];
  leftovers?: CookedLeftovers | null;
  feedback?: CookedFeedback | null;
}
export interface CookedPantryOutcome {
  pantryItemId: string;
  outcome: PantryOutcome;
}
export interface CookedMealOut {
  mealPlanEntry?: ReadPlanEntry | null;
  removedItemIds?: string[];
  keptItems?: PantryItemOut[];
  leftover?: PantryItemOut | null;
  feedback?: RecipeFeedbackOut | null;
}
export interface ReadPlanEntry {
  date: string;
  entryType?: PlanEntryType;
  title?: string;
  text?: string;
  recipeId?: string | null;
  recipeScale?: number;
  id: number;
  groupId: string;
  userId: string;
  householdId: string;
  recipe?: RecipeSummary | null;
  cookedAt?: string | null;
}
export interface RecipeSummary {
  id?: string | null;
  userId?: string;
  householdId?: string;
  groupId?: string;
  name?: string | null;
  slug?: string;
  image?: unknown;
  recipeServings?: number;
  recipeYieldQuantity?: number;
  recipeYield?: string | null;
  totalTime?: string | null;
  prepTime?: string | null;
  cookTime?: string | null;
  performTime?: string | null;
  totalTimeSeconds?: number | null;
  prepTimeSeconds?: number | null;
  performTimeSeconds?: number | null;
  description?: string | null;
  recipeCategory?: RecipeCategory[] | null;
  tags?: RecipeTag[] | null;
  tools?: RecipeTool[];
  rating?: number | null;
  orgURL?: string | null;
  dateAdded?: string | null;
  dateUpdated?: string | null;
  createdAt?: string | null;
  updatedAt?: string | null;
}
export interface RecipeCategory {
  id?: string | null;
  groupId?: string | null;
  name: string;
  slug: string;
  recipeCount?: number;
}
export interface RecipeTag {
  id?: string | null;
  groupId?: string | null;
  name: string;
  slug: string;
  recipeCount?: number;
}
export interface RecipeTool {
  id: string;
  groupId?: string | null;
  name: string;
  slug: string;
  recipeCount?: number;
  householdsWithTool?: string[];
}
export interface PantryItemOut {
  name: string;
  foodId?: string | null;
  quantity?: number | null;
  unitId?: string | null;
  location?: PantryLocation;
  boughtOn?: string | null;
  openedOn?: string | null;
  useBy?: string | null;
  source?: PantrySource;
  note?: string | null;
  id: string;
  groupId: string;
  householdId: string;
  food?: IngredientFood | null;
  unit?: IngredientUnit | null;
  createdAt?: string | null;
  updatedAt?: string | null;
}
export interface IngredientFood {
  id: string;
  name: string;
  pluralName?: string | null;
  description?: string;
  extras?: {
    [k: string]: unknown;
  } | null;
  labelId?: string | null;
  aliases?: IngredientFoodAlias[];
  substitutions?: IngredientFoodSubstitution[];
  householdsWithIngredientFood?: string[];
  label?: MultiPurposeLabelSummary | null;
  recipeCount?: number;
  createdAt?: string | null;
  updatedAt?: string | null;
}
export interface IngredientFoodAlias {
  name: string;
}
export interface IngredientFoodSubstitution {
  substituteFoodId?: string | null;
  note?: string | null;
  substituteFood?: IngredientFoodSummary | null;
}
export interface IngredientFoodSummary {
  id: string;
  name: string;
  pluralName?: string | null;
}
export interface MultiPurposeLabelSummary {
  name: string;
  color?: string;
  groupId: string;
  id: string;
}
export interface IngredientUnit {
  id: string;
  name: string;
  pluralName?: string | null;
  description?: string;
  extras?: {
    [k: string]: unknown;
  } | null;
  fraction?: boolean;
  abbreviation?: string;
  pluralAbbreviation?: string | null;
  useAbbreviation?: boolean;
  aliases?: IngredientUnitAlias[];
  standardQuantity?: number | null;
  standardUnit?: string | null;
  createdAt?: string | null;
  updatedAt?: string | null;
}
export interface IngredientUnitAlias {
  name: string;
}
export interface RecipeFeedbackOut {
  id: string;
  groupId: string;
  householdId: string;
  recipeId: string;
  userId?: string | null;
  verdict: FeedbackVerdict;
  effort?: number | null;
  note?: string | null;
  forWhom?: string | null;
  madeOn: string;
  timelineEventId?: string | null;
  recipe: RecipeFeedbackRecipe;
  userName?: string | null;
  createdAt?: string | null;
  updatedAt?: string | null;
}
export interface RecipeFeedbackRecipe {
  id: string;
  slug: string;
  name: string;
}
export interface CreateGroupRecipeAction {
  actionType: GroupRecipeActionType;
  title: string;
  url: string;
}
export interface CreateHouseholdPreferences {
  privateHousehold?: boolean;
  showAnnouncements?: boolean;
  lockRecipeEditsFromOtherHouseholds?: boolean;
  firstDayOfWeek?: number;
  recipePublic?: boolean;
  recipeShowNutrition?: boolean;
  recipeShowAssets?: boolean;
  recipeLandscapeView?: boolean;
  recipeDisableComments?: boolean;
}
export interface CreateInviteToken {
  uses: number;
  groupId?: string | null;
  householdId?: string | null;
}
export interface CreateWebhook {
  enabled?: boolean;
  name?: string;
  url?: string;
  webhookType?: WebhookType;
  scheduledTime: string;
}
export interface EmailInitationResponse {
  success: boolean;
  error?: string | null;
}
export interface EmailInvitation {
  email: string;
  token: string;
}
export interface GroupEventNotifierCreate {
  name: string;
  appriseUrl?: string | null;
}
export interface GroupEventNotifierOptions {
  testMessage?: boolean;
  webhookTask?: boolean;
  recipeCreated?: boolean;
  recipeUpdated?: boolean;
  recipeDeleted?: boolean;
  userSignup?: boolean;
  dataMigrations?: boolean;
  dataExport?: boolean;
  dataImport?: boolean;
  mealplanEntryCreated?: boolean;
  mealplanEntryUpdated?: boolean;
  mealplanEntryDeleted?: boolean;
  shoppingListCreated?: boolean;
  shoppingListUpdated?: boolean;
  shoppingListDeleted?: boolean;
  cookbookCreated?: boolean;
  cookbookUpdated?: boolean;
  cookbookDeleted?: boolean;
  tagCreated?: boolean;
  tagUpdated?: boolean;
  tagDeleted?: boolean;
  categoryCreated?: boolean;
  categoryUpdated?: boolean;
  categoryDeleted?: boolean;
  labelCreated?: boolean;
  labelUpdated?: boolean;
  labelDeleted?: boolean;
}
export interface GroupEventNotifierOptionsOut {
  testMessage?: boolean;
  webhookTask?: boolean;
  recipeCreated?: boolean;
  recipeUpdated?: boolean;
  recipeDeleted?: boolean;
  userSignup?: boolean;
  dataMigrations?: boolean;
  dataExport?: boolean;
  dataImport?: boolean;
  mealplanEntryCreated?: boolean;
  mealplanEntryUpdated?: boolean;
  mealplanEntryDeleted?: boolean;
  shoppingListCreated?: boolean;
  shoppingListUpdated?: boolean;
  shoppingListDeleted?: boolean;
  cookbookCreated?: boolean;
  cookbookUpdated?: boolean;
  cookbookDeleted?: boolean;
  tagCreated?: boolean;
  tagUpdated?: boolean;
  tagDeleted?: boolean;
  categoryCreated?: boolean;
  categoryUpdated?: boolean;
  categoryDeleted?: boolean;
  labelCreated?: boolean;
  labelUpdated?: boolean;
  labelDeleted?: boolean;
  id: string;
}
export interface GroupEventNotifierOptionsSave {
  testMessage?: boolean;
  webhookTask?: boolean;
  recipeCreated?: boolean;
  recipeUpdated?: boolean;
  recipeDeleted?: boolean;
  userSignup?: boolean;
  dataMigrations?: boolean;
  dataExport?: boolean;
  dataImport?: boolean;
  mealplanEntryCreated?: boolean;
  mealplanEntryUpdated?: boolean;
  mealplanEntryDeleted?: boolean;
  shoppingListCreated?: boolean;
  shoppingListUpdated?: boolean;
  shoppingListDeleted?: boolean;
  cookbookCreated?: boolean;
  cookbookUpdated?: boolean;
  cookbookDeleted?: boolean;
  tagCreated?: boolean;
  tagUpdated?: boolean;
  tagDeleted?: boolean;
  categoryCreated?: boolean;
  categoryUpdated?: boolean;
  categoryDeleted?: boolean;
  labelCreated?: boolean;
  labelUpdated?: boolean;
  labelDeleted?: boolean;
  notifierId: string;
}
export interface GroupEventNotifierOut {
  id: string;
  name: string;
  enabled: boolean;
  groupId: string;
  householdId: string;
  options: GroupEventNotifierOptionsOut;
}
export interface GroupEventNotifierPrivate {
  id: string;
  name: string;
  enabled: boolean;
  groupId: string;
  householdId: string;
  options: GroupEventNotifierOptionsOut;
  appriseUrl: string;
}
export interface GroupEventNotifierSave {
  name: string;
  appriseUrl?: string | null;
  enabled?: boolean;
  groupId: string;
  householdId: string;
  options?: GroupEventNotifierOptions;
}
export interface GroupEventNotifierUpdate {
  name: string;
  appriseUrl?: string | null;
  enabled?: boolean;
  groupId: string;
  householdId: string;
  options?: GroupEventNotifierOptions;
  id: string;
}
export interface GroupRecipeActionOut {
  actionType: GroupRecipeActionType;
  title: string;
  url: string;
  groupId: string;
  householdId: string;
  id: string;
}
export interface GroupRecipeActionPayload {
  action: GroupRecipeActionOut;
  content: unknown;
  recipeScale: number;
}
export interface HouseholdCreate {
  groupId?: string | null;
  name: string;
}
export interface HouseholdInDB {
  groupId: string;
  name: string;
  id: string;
  slug: string;
  preferences?: ReadHouseholdPreferences | null;
  group: string;
  users?: HouseholdUserSummary[] | null;
  webhooks?: ReadWebhook[];
}
export interface ReadHouseholdPreferences {
  privateHousehold?: boolean;
  showAnnouncements?: boolean;
  lockRecipeEditsFromOtherHouseholds?: boolean;
  firstDayOfWeek?: number;
  recipePublic?: boolean;
  recipeShowNutrition?: boolean;
  recipeShowAssets?: boolean;
  recipeLandscapeView?: boolean;
  recipeDisableComments?: boolean;
  id: string;
}
export interface HouseholdUserSummary {
  id: string;
  fullName: string;
}
export interface ReadWebhook {
  enabled?: boolean;
  name?: string;
  url?: string;
  webhookType?: WebhookType;
  scheduledTime: string;
  groupId: string;
  householdId: string;
  id: string;
}
export interface HouseholdProfileOut {
  members?: MemberProfileOut[];
  preferences?: MealPreferencesOut | null;
}
export interface MemberProfileOut {
  id: string;
  groupId: string;
  householdId: string;
  userId?: string | null;
  name: string;
  isChild?: boolean;
  diet?: Diet;
  allergies?: string[];
  exclusions?: string[];
  dislikes?: string[];
  likes?: string[];
  notes?: string | null;
  position?: number;
  createdAt?: string | null;
  updatedAt?: string | null;
}
export interface MealPreferencesOut {
  id: string;
  groupId: string;
  householdId: string;
  defaultServings?: number | null;
  quickWeekdays?: number[];
  weeknightMaxMinutes?: number | null;
  weekendMaxMinutes?: number | null;
  favouriteCuisines?: string[];
  notes?: string | null;
  createdAt?: string | null;
  updatedAt?: string | null;
}
export interface HouseholdRecipeBase {
  lastMade?: string | null;
}
export interface HouseholdRecipeCreate {
  lastMade?: string | null;
  householdId: string;
  recipeId: string;
}
export interface HouseholdRecipeOut {
  lastMade?: string | null;
  householdId: string;
  recipeId: string;
  id: string;
}
export interface HouseholdRecipeSummary {
  lastMade?: string | null;
  recipeId: string;
}
export interface HouseholdRecipeUpdate {
  lastMade?: string | null;
}
export interface HouseholdSave {
  groupId: string;
  name: string;
}
export interface HouseholdStatistics {
  totalRecipes: number;
  totalUsers: number;
  totalCategories: number;
  totalTags: number;
  totalTools: number;
}
export interface HouseholdSummary {
  groupId: string;
  name: string;
  id: string;
  slug: string;
  preferences?: ReadHouseholdPreferences | null;
}
export interface MealPreferencesUpdate {
  defaultServings?: number | null;
  quickWeekdays?: number[] | null;
  weeknightMaxMinutes?: number | null;
  weekendMaxMinutes?: number | null;
  favouriteCuisines?: string[] | null;
  notes?: string | null;
}
export interface MemberProfileCreate {
  name: string;
  userId?: string | null;
  isChild?: boolean;
  diet?: Diet;
  allergies?: string[];
  exclusions?: string[];
  dislikes?: string[];
  likes?: string[];
  notes?: string | null;
  position?: number;
}
export interface MemberProfileUpdate {
  name?: string | null;
  userId?: string | null;
  isChild?: boolean | null;
  diet?: Diet | null;
  allergies?: string[] | null;
  exclusions?: string[] | null;
  dislikes?: string[] | null;
  likes?: string[] | null;
  notes?: string | null;
  position?: number | null;
}
export interface PantryCheckOut {
  items: PantryItemOut[];
  suggestedLeftoverPortions: number;
  mealPlanEntryId?: number | null;
  ingredients?: PantryIngredientMatch[];
}
export interface PantryIngredientMatch {
  referenceId: string;
  pantryItemIds?: string[];
}
export interface PantryItemCreate {
  name: string;
  foodId?: string | null;
  quantity?: number | null;
  unitId?: string | null;
  location?: PantryLocation;
  boughtOn?: string | null;
  openedOn?: string | null;
  useBy?: string | null;
  source?: PantrySource;
  note?: string | null;
}
export interface PantryItemUpdate {
  name: string;
  foodId?: string | null;
  quantity?: number | null;
  unitId?: string | null;
  location?: PantryLocation;
  boughtOn?: string | null;
  openedOn?: string | null;
  useBy?: string | null;
  source?: PantrySource;
  note?: string | null;
}
export interface PutAwayRequest {
  itemIds?: string[] | null;
}
export interface PutAwayResult {
  created: PantryItemOut[];
  merged: PantryItemOut[];
  removedItemIds: string[];
}
export interface ReadInviteToken {
  token: string;
  usesLeft: number;
  groupId: string;
  householdId: string;
}
export interface RecipeFeedbackCreate {
  recipeId: string;
  verdict: FeedbackVerdict;
  effort?: number | null;
  note?: string | null;
  forWhom?: string | null;
  madeOn?: string | null;
}
export interface RecipeFeedbackSummary {
  lastVerdict: FeedbackVerdict;
  lastMadeOn: string;
  loved?: number;
  ok?: number;
  neverAgain?: number;
  total?: number;
}
export interface SaveGroupRecipeAction {
  actionType: GroupRecipeActionType;
  title: string;
  url: string;
  groupId: string;
  householdId: string;
}
export interface SaveHouseholdPreferences {
  privateHousehold?: boolean;
  showAnnouncements?: boolean;
  lockRecipeEditsFromOtherHouseholds?: boolean;
  firstDayOfWeek?: number;
  recipePublic?: boolean;
  recipeShowNutrition?: boolean;
  recipeShowAssets?: boolean;
  recipeLandscapeView?: boolean;
  recipeDisableComments?: boolean;
  householdId: string;
}
export interface SaveInviteToken {
  usesLeft: number;
  groupId: string;
  householdId: string;
  token: string;
}
export interface SaveWebhook {
  enabled?: boolean;
  name?: string;
  url?: string;
  webhookType?: WebhookType;
  scheduledTime: string;
  groupId: string;
  householdId: string;
}
export interface SetPermissions {
  userId: string;
  canManageHousehold?: boolean;
  canManage?: boolean;
  canInvite?: boolean;
  canOrganize?: boolean;
}
export interface ShoppingListAddRecipeParams {
  recipeIncrementQuantity?: number;
  recipeIngredients?: RecipeIngredient[] | null;
}
export interface RecipeIngredient {
  quantity?: number | null;
  unit?: IngredientUnit | CreateIngredientUnit | null;
  food?: IngredientFood | CreateIngredientFood | null;
  referencedRecipe?: Recipe | null;
  note?: string | null;
  display?: string;
  title?: string | null;
  originalText?: string | null;
  substitutions?: RecipeIngredientSubstitution[];
  referenceId?: string;
}
export interface CreateIngredientUnit {
  id?: string | null;
  name: string;
  pluralName?: string | null;
  description?: string;
  extras?: {
    [k: string]: unknown;
  } | null;
  fraction?: boolean;
  abbreviation?: string;
  pluralAbbreviation?: string | null;
  useAbbreviation?: boolean;
  aliases?: CreateIngredientUnitAlias[];
  standardQuantity?: number | null;
  standardUnit?: string | null;
}
export interface CreateIngredientUnitAlias {
  name: string;
}
export interface CreateIngredientFood {
  id?: string | null;
  name: string;
  pluralName?: string | null;
  description?: string;
  extras?: {
    [k: string]: unknown;
  } | null;
  labelId?: string | null;
  aliases?: CreateIngredientFoodAlias[];
  substitutions?: CreateIngredientFoodSubstitution[];
  householdsWithIngredientFood?: string[];
}
export interface CreateIngredientFoodAlias {
  name: string;
}
export interface CreateIngredientFoodSubstitution {
  substituteFoodId?: string | null;
  note?: string | null;
}
export interface Recipe {
  id?: string | null;
  userId?: string;
  householdId?: string;
  groupId?: string;
  name?: string | null;
  slug?: string;
  image?: unknown;
  recipeServings?: number;
  recipeYieldQuantity?: number;
  recipeYield?: string | null;
  totalTime?: string | null;
  prepTime?: string | null;
  cookTime?: string | null;
  performTime?: string | null;
  totalTimeSeconds?: number | null;
  prepTimeSeconds?: number | null;
  performTimeSeconds?: number | null;
  description?: string | null;
  recipeCategory?: RecipeCategory[] | null;
  tags?: RecipeTag[] | null;
  tools?: RecipeTool[];
  rating?: number | null;
  orgURL?: string | null;
  dateAdded?: string | null;
  dateUpdated?: string | null;
  createdAt?: string | null;
  updatedAt?: string | null;
  recipeIngredient?: RecipeIngredient[];
  recipeInstructions?: RecipeStep[] | null;
  nutrition?: Nutrition | null;
  settings?: RecipeSettings | null;
  assets?: RecipeAsset[] | null;
  notes?: RecipeNote[] | null;
  extras?: {
    [k: string]: unknown;
  } | null;
  comments?: RecipeCommentOut[] | null;
}
export interface RecipeStep {
  id?: string | null;
  title?: string | null;
  summary?: string | null;
  text: string;
  ingredientReferences?: IngredientReferences[];
  noteReferences?: NoteReference[];
  durationSeconds?: number | null;
}
export interface IngredientReferences {
  referenceId?: string | null;
}
export interface NoteReference {
  referenceId?: string | null;
}
export interface Nutrition {
  calories?: string | null;
  carbohydrateContent?: string | null;
  cholesterolContent?: string | null;
  fatContent?: string | null;
  fiberContent?: string | null;
  proteinContent?: string | null;
  saturatedFatContent?: string | null;
  sodiumContent?: string | null;
  sugarContent?: string | null;
  transFatContent?: string | null;
  unsaturatedFatContent?: string | null;
}
export interface RecipeSettings {
  public?: boolean;
  showNutrition?: boolean;
  showAssets?: boolean;
  landscapeView?: boolean;
  disableComments?: boolean;
  locked?: boolean;
}
export interface RecipeAsset {
  name: string;
  icon: string;
  fileName?: string | null;
}
export interface RecipeNote {
  title: string;
  text: string;
  referenceId?: string;
}
export interface RecipeCommentOut {
  id: string;
  recipeId: string;
  text: string;
  createdAt: string;
  updatedAt: string;
  userId: string;
  user: UserBase;
}
export interface UserBase {
  id: string;
  username?: string | null;
  admin: boolean;
  fullName?: string | null;
}
export interface RecipeIngredientSubstitution {
  substituteFoodId?: string | null;
  note?: string | null;
  substituteFood?: IngredientFoodSummary | null;
}
export interface ShoppingListAddRecipeParamsBulk {
  recipeIncrementQuantity?: number;
  recipeIngredients?: RecipeIngredient[] | null;
  recipeId: string;
}
export interface ShoppingListCreate {
  name?: string | null;
  extras?: {
    [k: string]: unknown;
  } | null;
  createdAt?: string | null;
  updatedAt?: string | null;
}
export interface ShoppingListItemBase {
  quantity?: number;
  unit?: IngredientUnit | CreateIngredientUnit | null;
  food?: IngredientFood | CreateIngredientFood | null;
  referencedRecipe?: Recipe | null;
  note?: string | null;
  display?: string;
  shoppingListId: string;
  checked?: boolean;
  position?: number;
  foodId?: string | null;
  labelId?: string | null;
  unitId?: string | null;
  extras?: {
    [k: string]: unknown;
  } | null;
}
export interface ShoppingListItemCreate {
  quantity?: number;
  unit?: IngredientUnit | CreateIngredientUnit | null;
  food?: IngredientFood | CreateIngredientFood | null;
  referencedRecipe?: Recipe | null;
  note?: string | null;
  display?: string;
  shoppingListId: string;
  checked?: boolean;
  position?: number;
  foodId?: string | null;
  labelId?: string | null;
  unitId?: string | null;
  extras?: {
    [k: string]: unknown;
  } | null;
  id?: string | null;
  recipeReferences?: ShoppingListItemRecipeRefCreate[];
}
export interface ShoppingListItemRecipeRefCreate {
  recipeId: string;
  recipeQuantity?: number;
  recipeScale?: number | null;
  recipeNote?: string | null;
}
export interface ShoppingListItemOut {
  quantity?: number;
  unit?: IngredientUnit | null;
  food?: IngredientFood | null;
  referencedRecipe?: Recipe | null;
  note?: string | null;
  display?: string;
  shoppingListId: string;
  checked?: boolean;
  position?: number;
  foodId?: string | null;
  labelId?: string | null;
  unitId?: string | null;
  extras?: {
    [k: string]: unknown;
  } | null;
  id: string;
  groupId: string;
  householdId: string;
  label?: MultiPurposeLabelSummary | null;
  recipeReferences?: ShoppingListItemRecipeRefOut[];
  createdAt?: string | null;
  updatedAt?: string | null;
}
export interface ShoppingListItemRecipeRefOut {
  recipeId: string;
  recipeQuantity?: number;
  recipeScale?: number | null;
  recipeNote?: string | null;
  id: string;
  shoppingListItemId: string;
}
export interface ShoppingListItemRecipeRefUpdate {
  recipeId: string;
  recipeQuantity?: number;
  recipeScale?: number | null;
  recipeNote?: string | null;
  id: string;
  shoppingListItemId: string;
}
export interface ShoppingListItemUpdate {
  quantity?: number;
  unit?: IngredientUnit | CreateIngredientUnit | null;
  food?: IngredientFood | CreateIngredientFood | null;
  referencedRecipe?: Recipe | null;
  note?: string | null;
  display?: string;
  shoppingListId: string;
  checked?: boolean;
  position?: number;
  foodId?: string | null;
  labelId?: string | null;
  unitId?: string | null;
  extras?: {
    [k: string]: unknown;
  } | null;
  recipeReferences?: (ShoppingListItemRecipeRefCreate | ShoppingListItemRecipeRefUpdate)[];
}
export interface ShoppingListItemUpdateBulk {
  quantity?: number;
  unit?: IngredientUnit | CreateIngredientUnit | null;
  food?: IngredientFood | CreateIngredientFood | null;
  referencedRecipe?: Recipe | null;
  note?: string | null;
  display?: string;
  shoppingListId: string;
  checked?: boolean;
  position?: number;
  foodId?: string | null;
  labelId?: string | null;
  unitId?: string | null;
  extras?: {
    [k: string]: unknown;
  } | null;
  recipeReferences?: (ShoppingListItemRecipeRefCreate | ShoppingListItemRecipeRefUpdate)[];
  id: string;
}
export interface ShoppingListItemsCollectionOut {
  createdItems?: ShoppingListItemOut[];
  updatedItems?: ShoppingListItemOut[];
  deletedItems?: ShoppingListItemOut[];
}
export interface ShoppingListMultiPurposeLabelCreate {
  shoppingListId: string;
  labelId: string;
  position?: number;
}
export interface ShoppingListMultiPurposeLabelOut {
  shoppingListId: string;
  labelId: string;
  position?: number;
  id: string;
  label: MultiPurposeLabelSummary;
}
export interface ShoppingListMultiPurposeLabelUpdate {
  shoppingListId: string;
  labelId: string;
  position?: number;
  id: string;
}
export interface ShoppingListOut {
  name?: string | null;
  extras?: {
    [k: string]: unknown;
  } | null;
  createdAt?: string | null;
  updatedAt?: string | null;
  groupId: string;
  userId: string;
  id: string;
  listItems?: ShoppingListItemOut[];
  householdId: string;
  recipeReferences?: ShoppingListRecipeRefOut[];
  labelSettings?: ShoppingListMultiPurposeLabelOut[];
}
export interface ShoppingListRecipeRefOut {
  id: string;
  shoppingListId: string;
  recipeId: string;
  recipeQuantity: number;
  recipe: RecipeSummary;
}
export interface ShoppingListRemoveRecipeParams {
  recipeDecrementQuantity?: number;
}
export interface ShoppingListSave {
  name?: string | null;
  extras?: {
    [k: string]: unknown;
  } | null;
  createdAt?: string | null;
  updatedAt?: string | null;
  groupId: string;
  userId: string;
}
export interface ShoppingListSummary {
  name?: string | null;
  extras?: {
    [k: string]: unknown;
  } | null;
  createdAt?: string | null;
  updatedAt?: string | null;
  groupId: string;
  userId: string;
  id: string;
  householdId: string;
  recipeReferences: ShoppingListRecipeRefOut[];
  labelSettings: ShoppingListMultiPurposeLabelOut[];
}
export interface ShoppingListUpdate {
  name?: string | null;
  extras?: {
    [k: string]: unknown;
  } | null;
  createdAt?: string | null;
  updatedAt?: string | null;
  groupId: string;
  userId: string;
  id: string;
  listItems?: ShoppingListItemOut[];
}
export interface UpdateHousehold {
  groupId: string;
  name: string;
  id: string;
  slug: string;
}
export interface UpdateHouseholdAdmin {
  groupId: string;
  name: string;
  id: string;
  preferences?: UpdateHouseholdPreferences | null;
}
export interface UpdateHouseholdPreferences {
  privateHousehold?: boolean;
  showAnnouncements?: boolean;
  lockRecipeEditsFromOtherHouseholds?: boolean;
  firstDayOfWeek?: number;
  recipePublic?: boolean;
  recipeShowNutrition?: boolean;
  recipeShowAssets?: boolean;
  recipeLandscapeView?: boolean;
  recipeDisableComments?: boolean;
}
export interface RecipeIngredientBase {
  quantity?: number | null;
  unit?: IngredientUnit | CreateIngredientUnit | null;
  food?: IngredientFood | CreateIngredientFood | null;
  referencedRecipe?: Recipe | null;
  note?: string | null;
  display?: string;
}
