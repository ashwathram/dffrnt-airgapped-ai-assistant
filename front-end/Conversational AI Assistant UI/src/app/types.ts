export interface TagType {
  id: string;
  name: string;
  color: string;
  description?: string;
}

export interface Tag {
  id: string;
  name: string;
  typeId: string;
}

export interface Document {
  id: string;
  name: string;
  type: "pdf" | "xlsx" | "docx" | "txt";
  size: string;
  sizeBytes: number;
  uploadedAt: string;
  uploadedAtMs: number;      // for sort order
  uploadedBy: string;
  pages?: number;
  tagIds: string[];
  description: string;
  usedInChats: number;
  contentHash?: string;
  fromFolder?: string;       // folder name if extracted from a folder upload
}

export const DEFAULT_TAG_TYPES: TagType[] = [
  { id: "tt-1", name: "Department", color: "#5D27B8", description: "Organizational unit" },
  { id: "tt-2", name: "Document Type", color: "#E72300", description: "Nature of the document" },
  { id: "tt-3", name: "Period", color: "#091A29", description: "Time period covered" },
  { id: "tt-4", name: "Confidentiality", color: "#0a7c4a", description: "Access level" },
];

export const DEFAULT_TAGS: Tag[] = [
  { id: "t-1", name: "Finance", typeId: "tt-1" },
  { id: "t-2", name: "Legal", typeId: "tt-1" },
  { id: "t-3", name: "Product", typeId: "tt-1" },
  { id: "t-4", name: "HR", typeId: "tt-1" },
  { id: "t-5", name: "Marketing", typeId: "tt-1" },
  { id: "t-6", name: "Report", typeId: "tt-2" },
  { id: "t-7", name: "Policy", typeId: "tt-2" },
  { id: "t-8", name: "Contract", typeId: "tt-2" },
  { id: "t-9", name: "Analysis", typeId: "tt-2" },
  { id: "t-10", name: "Roadmap", typeId: "tt-2" },
  { id: "t-11", name: "Q3 2024", typeId: "tt-3" },
  { id: "t-12", name: "Q4 2024", typeId: "tt-3" },
  { id: "t-13", name: "2025", typeId: "tt-3" },
  { id: "t-14", name: "2026", typeId: "tt-3" },
  { id: "t-15", name: "Internal", typeId: "tt-4" },
  { id: "t-16", name: "Confidential", typeId: "tt-4" },
  { id: "t-17", name: "Public", typeId: "tt-4" },
];

export const DEFAULT_DOCUMENTS: Document[] = [
  {
    id: "doc-1",
    name: "Q3 2024 Financial Report.pdf",
    type: "pdf",
    size: "4.2 MB",
    sizeBytes: 4404019,
    uploadedAt: "Jun 8, 2026",
    uploadedAtMs: new Date("2026-06-08").getTime(),
    uploadedBy: "System",
    pages: 84,
    tagIds: ["t-1", "t-6", "t-11", "t-15"],
    description: "Comprehensive Q3 financial performance overview including revenue, margins, and regional breakdown.",
    usedInChats: 12,
    contentHash: "hash-001",
  },
  {
    id: "doc-2",
    name: "Product Roadmap 2026.pdf",
    type: "pdf",
    size: "1.8 MB",
    sizeBytes: 1887436,
    uploadedAt: "Jun 5, 2026",
    uploadedAtMs: new Date("2026-06-05").getTime(),
    uploadedBy: "System",
    pages: 32,
    tagIds: ["t-3", "t-10", "t-14", "t-15"],
    description: "Strategic product initiatives and feature delivery timeline for FY2026.",
    usedInChats: 8,
    contentHash: "hash-002",
  },
  {
    id: "doc-3",
    name: "Customer Survey Results.xlsx",
    type: "xlsx",
    size: "890 KB",
    sizeBytes: 911360,
    uploadedAt: "Jun 1, 2026",
    uploadedAtMs: new Date("2026-06-01").getTime(),
    uploadedBy: "System",
    tagIds: ["t-5", "t-9", "t-13"],
    description: "Aggregated NPS and CSAT survey data from 1,200 enterprise customers.",
    usedInChats: 5,
    contentHash: "hash-003",
  },
  {
    id: "doc-4",
    name: "Legal Framework Overview.pdf",
    type: "pdf",
    size: "2.1 MB",
    sizeBytes: 2202009,
    uploadedAt: "May 28, 2026",
    uploadedAtMs: new Date("2026-05-28").getTime(),
    uploadedBy: "System",
    pages: 61,
    tagIds: ["t-2", "t-8", "t-16"],
    description: "Summary of applicable regulatory frameworks and compliance obligations for EU and APAC operations.",
    usedInChats: 3,
    contentHash: "hash-004",
  },
  {
    id: "doc-5",
    name: "Market Analysis Report.pdf",
    type: "pdf",
    size: "5.7 MB",
    sizeBytes: 5978112,
    uploadedAt: "May 22, 2026",
    uploadedAtMs: new Date("2026-05-22").getTime(),
    uploadedBy: "System",
    pages: 118,
    tagIds: ["t-5", "t-9", "t-14"],
    description: "Third-party analysis of total addressable market, competitive landscape, and growth opportunities.",
    usedInChats: 7,
    contentHash: "hash-005",
  },
  {
    id: "doc-6",
    name: "HR Policy Manual.docx",
    type: "docx",
    size: "620 KB",
    sizeBytes: 634880,
    uploadedAt: "May 15, 2026",
    uploadedAtMs: new Date("2026-05-15").getTime(),
    uploadedBy: "System",
    tagIds: ["t-4", "t-7", "t-15"],
    description: "Employee handbook covering conduct, benefits, leave policies, and performance management.",
    usedInChats: 2,
    contentHash: "hash-006",
  },
];
